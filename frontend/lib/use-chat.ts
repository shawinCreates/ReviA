/**
 * Chat state: conversations, the transcript, and the one request that matters.
 *
 * The user's turn is added locally and reconciled against the server on the next
 * successful answer rather than re-fetched. A question takes seconds to answer,
 * and a spinner over an empty box for that long reads as broken.
 */

"use client";

import { useCallback, useRef, useState } from "react";

import { ApiError, askQuestion, fetchSessionMessages, fetchSessions } from "@/lib/api";
import type { ChatSession, Message } from "@/lib/types";

type Options = {
  signedIn: boolean;
  initialSessions: ChatSession[];
  initialMessages: Message[];
  initialSessionId: string | null;
  libraryId?: string | null;
  fallbackSessions: ChatSession[];
  fallbackMessages: Message[];
};

export function useChat({
  signedIn,
  initialSessions,
  initialMessages,
  initialSessionId,
  libraryId,
  fallbackSessions,
  fallbackMessages,
}: Options) {
  const [sessions, setSessions] = useState<ChatSession[]>(initialSessions);
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [activeId, setActiveId] = useState<string | null>(initialSessionId);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Set when the user pressed "New conversation": the next question must start a
  // fresh session rather than fall back to the latest one.
  const startFresh = useRef(false);

  const refreshSessions = useCallback(async () => {
    if (!signedIn) return;
    try {
      setSessions(await fetchSessions());
    } catch {
      // The sidebar is a convenience. Losing it should not interrupt an answer
      // already in flight.
    }
  }, [signedIn]);

  const ask = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || pending || !signedIn) return;

      setError(null);
      setPending(true);

      const optimistic: Message = {
        id: `local-${crypto.randomUUID()}`,
        role: "user",
        content: text,
        citations: [],
        refused: false,
        uncited: false,
        createdAt: new Date().toISOString(),
      };
      setMessages((current) => [...current, optimistic]);

      try {
        const result = await askQuestion(text, {
          sessionId: startFresh.current ? null : activeId,
          libraryId,
        });
        // Re-read the flag: the user may have pressed "New conversation" while
        // the answer was being generated, and that intent should still win for
        // the next turn.
        const fresh = startFresh.current;
        startFresh.current = false;

        setMessages((current) => [...current, result.message]);
        setActiveId(result.sessionId);
        setSessions((current) => {
          const known = current.find((entry) => entry.id === result.sessionId);
          if (!known) {
            return [
              {
                id: result.sessionId,
                title: result.sessionTitle,
                createdAt: new Date().toISOString(),
                messageCount: 2,
              },
              ...current,
            ];
          }
          return current.map((entry) =>
            entry.id === result.sessionId
              ? { ...entry, messageCount: entry.messageCount + 2 }
              : entry,
          );
        });

        // A fresh session changes the ordering of the sidebar, and the server
        // holds the real titles and counts.
        if (fresh) void refreshSessions();
      } catch (cause) {
        const failure = cause as ApiError;
        setError(failure.message);
        // The question is kept on the composer so it can be retried, and the
        // optimistic turn is dropped: leaving it there would imply it was asked.
        setMessages((current) => current.filter((entry) => entry.id !== optimistic.id));
      } finally {
        setPending(false);
      }
    },
    [activeId, libraryId, pending, refreshSessions, signedIn],
  );

  const selectSession = useCallback(
    async (id: string) => {
      if (id === activeId) return;
      startFresh.current = false;
      setActiveId(id);
      setError(null);

      try {
        setMessages(await fetchSessionMessages(id));
      } catch (cause) {
        setError((cause as ApiError).message);
        setMessages([]);
      }
    },
    [activeId],
  );

  const newConversation = useCallback(() => {
    startFresh.current = true;
    setActiveId(null);
    setMessages([]);
    setError(null);
  }, []);

  // No reset effect for sign-out: the returned values already fall back to the
  // sample data when `signedIn` is false, so nothing is ever displayed, and
  // signing out is a navigation that rebuilds this hook with empty server data.
  // A `setState`-in-effect here would only restate what the return already does.

  return {
    sessions: signedIn ? sessions : fallbackSessions,
    messages: signedIn ? messages : fallbackMessages,
    activeId,
    pending,
    error,
    dismissError: () => setError(null),
    ask,
    selectSession,
    newConversation,
    refreshSessions,
  };
}

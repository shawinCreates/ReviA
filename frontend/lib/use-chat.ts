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
  const startFresh = useRef(false);

  const refreshSessions = useCallback(async () => {
    if (!signedIn) return;
    try {
      setSessions(await fetchSessions());
    } catch {
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

        if (fresh) void refreshSessions();
      } catch (cause) {
        const failure = cause as ApiError;
        setError(failure.message);
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

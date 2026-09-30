"use client";

import { useEffect, useRef, useState } from "react";

import { DEMO_MESSAGES, DEMO_SESSIONS, SUGGESTED_QUESTIONS } from "@/lib/mock/data";
import type { ChatSession, Message } from "@/lib/types";
import { Send } from "@/components/icons";
import { Button } from "@/components/ui";

const CANDIDATE_ANSWER =
  "Yes. A minister exercising a statutory duty is a public body for judicial review [S1]. What changes is the intensity: a decision taken under a wide discretion is examined for rationality, not correctness [S2].";

export function ChatColumn({ signedIn }: { signedIn: boolean }) {
  const [messages, setMessages] = useState<Message[]>(DEMO_MESSAGES);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, pending]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;

    setDraft("");
    setPending(true);
    setMessages((current) => [
      ...current,
      {
        id: `local-${current.length}`,
        role: "user",
        content: question,
        citations: [],
        refused: false,
        uncited: false,
        createdAt: new Date().toISOString(),
      },
    ]);

    const isGuestQuestion = !signedIn;

    await new Promise((resolve) => setTimeout(resolve, 650));

    setMessages((current) => [
      ...current,
      {
        id: `local-${current.length}-a`,
        role: "assistant",
        content: CANDIDATE_ANSWER,
        citations: [
          {
            label: "S1",
            page: 7,
            documentId: "doc-natlaw",
            filename: "Constitutional Law — Week 4 Notes.pdf",
            snippet: "Public bodies include ministers exercising statutory duties.",
          },
          {
            label: "S2",
            page: 9,
            documentId: "doc-natlaw",
            filename: "Constitutional Law — Week 4 Notes.pdf",
            snippet: "Wider discretion narrows the court to a rationality review.",
          },
        ],
        refused: false,
        uncited: false,
        createdAt: new Date().toISOString(),
      },
    ]);

    if (isGuestQuestion) {
      setMessages((current) => [
        ...current,
        {
          id: `local-${current.length}-n`,
          role: "user",
          content: "This conversation is not being saved. Create an account to keep it.",
          citations: [],
          refused: false,
          uncited: false,
          createdAt: new Date().toISOString(),
        },
      ]);
    }

    setPending(false);
  }

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-canvas">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line px-5">
        <p className="truncate text-[13px] text-ink">Judicial review</p>
        {!signedIn ? (
          <span className="shrink-0 rounded-full bg-pale-yellow-bg px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.06em] text-pale-yellow-ink">
            Sample library
          </span>
        ) : null}
        <span className="ml-auto shrink-0 font-mono text-[11px] text-faint">4 sources</span>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-7">
        <div className="mx-auto max-w-[68ch] space-y-7">
          {messages.map((message) => (
            <MessageBlock key={message.id} message={message} />
          ))}

          {pending ? (
            <div className="flex items-center gap-2 text-[13px] text-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-faint" />
              Reading four documents
            </div>
          ) : null}
        </div>
      </div>

      <div className="shrink-0 border-t border-line bg-canvas px-5 py-4">
        <div className="mx-auto max-w-[68ch]">
          {!signedIn && messages.length <= 1 ? (
            <div className="mb-3 flex flex-wrap gap-2">
              {SUGGESTED_QUESTIONS.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => send(question)}
                  className="rounded-full border border-line bg-surface px-3 py-1.5 text-[12px] text-muted transition-colors hover:border-line-strong hover:text-ink"
                >
                  {question}
                </button>
              ))}
            </div>
          ) : null}

          <form
            onSubmit={(event) => {
              event.preventDefault();
              send(draft);
            }}
            className="flex items-end gap-2.5"
          >
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  send(draft);
                }
              }}
              rows={1}
              placeholder="Ask something your documents answer"
              className="max-h-40 min-h-11 flex-1 resize-none rounded-[6px] border border-line bg-surface px-3.5 py-3 text-[14px] leading-relaxed text-ink outline-none transition-colors placeholder:text-faint focus:border-ink"
            />
            <Button type="submit" disabled={!draft.trim() || pending} aria-label="Send">
              <Send size={15} />
            </Button>
          </form>
        </div>
      </div>
    </section>
  );
}

function MessageBlock({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[52ch] rounded-[8px] bg-ink px-4 py-2.5 text-[14px] leading-relaxed text-white">
          {message.content}
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="space-y-4 text-[14px] leading-[1.7] text-ink-soft">
        {message.content.split("\n\n").map((paragraph, index) => (
          <p key={index}>{paragraph}</p>
        ))}
      </div>

      {message.citations.length > 0 ? (
        <div className="mt-5 flex flex-wrap gap-2">
          {message.citations.map((citation) => (
            <div
              key={citation.label}
              className="max-w-[46ch] rounded-[8px] border border-line bg-surface p-3"
            >
              <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-pale-blue-ink">
                {citation.label} &middot; {citation.filename} &middot; p. {citation.page}
              </p>
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{citation.snippet}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function HistoryColumn({ signedIn }: { signedIn: boolean }) {
  const [sessions, setSessions] = useState<ChatSession[]>(DEMO_SESSIONS);
  const [activeId, setActiveId] = useState<string>(DEMO_SESSIONS[0].id);

  return (
    <aside className="hidden w-[248px] shrink-0 flex-col border-r border-line bg-surface lg:flex">
      <div className="flex h-11 shrink-0 items-center px-5">
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-faint">History</p>
      </div>

      <div className="flex-1 overflow-y-auto px-2.5 pb-4">
        {sessions.map((session) => {
          const active = session.id === activeId;
          return (
            <button
              key={session.id}
              type="button"
              onClick={() => setActiveId(session.id)}
              className={`mb-0.5 w-full rounded-[6px] px-3 py-2.5 text-left transition-colors ${
                active ? "bg-sunk" : "hover:bg-sunk/60"
              }`}
            >
              <span
                className={`block truncate text-[13px] ${active ? "text-ink" : "text-ink-soft"}`}
              >
                {session.title}
              </span>
              <span className="mt-0.5 block font-mono text-[10px] text-faint">
                {session.messageCount} messages
              </span>
            </button>
          );
        })}
      </div>

      <div className="shrink-0 border-t border-line p-3">
        {signedIn ? (
          <button
            type="button"
            onClick={() => {
              const next: ChatSession = {
                id: `local-${sessions.length}`,
                title: "New conversation",
                createdAt: new Date().toISOString(),
                messageCount: 0,
              };
              setSessions((current) => [next, ...current]);
              setActiveId(next.id);
            }}
            className="w-full rounded-[6px] border border-line px-3 py-2 text-[13px] text-ink transition-colors hover:border-line-strong hover:bg-sunk"
          >
            New conversation
          </button>
        ) : (
          <p className="px-1 text-[11px] leading-relaxed text-faint">
            Sign in and your conversations are kept between visits.
          </p>
        )}
      </div>
    </aside>
  );
}

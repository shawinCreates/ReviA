"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { AuthModal } from "@/components/auth-modal";
import { Plus, Send } from "@/components/icons";
import { Button } from "@/components/ui";
import type { ChatSession, Message } from "@/lib/types";

export const ASK_REASON =
  "Sign in and you can ask your own documents questions, with every answer kept between visits.";

export function ChatColumn({
  signedIn,
  messages,
  pending,
  error,
  onAsk,
  onDismissError,
  readyCount,
}: {
  signedIn: boolean;
  messages: Message[];
  pending: boolean;
  error: string | null;
  onAsk: (question: string) => void;
  onDismissError: () => void;
  readyCount: number;
}) {
  const [draft, setDraft] = useState("");
  const [authOpen, setAuthOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, pending]);

  // The advertised shortcut from the landing page. Scoped to this page so it
  // cannot swallow "/" while the user is typing a path or a fraction.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;

      event.preventDefault();
      inputRef.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const sourceCount = useMemo(() => {
    const lastAssistant = [...messages].reverse().find((entry) => entry.role === "assistant");
    return lastAssistant?.citations.length ?? 0;
  }, [messages]);

  const title = useMemo(() => {
    if (pending) return "Working";
    const lastUser = [...messages].reverse().find((entry) => entry.role === "user");
    if (!lastUser) return "New conversation";
    return lastUser.content.length > 48 ? `${lastUser.content.slice(0, 48).trimEnd()}…` : lastUser.content;
  }, [messages, pending]);

  function submit() {
    const question = draft.trim();
    if (!question) return;

    // A signed-out visitor cannot reach the API at all, so the honest response is
    // to ask them to sign in — not to simulate an answer.
    if (!signedIn) {
      setAuthOpen(false);
      setTimeout(() => setAuthOpen(true), 0);
      return;
    }
    if (pending) return;

    setDraft("");
    onAsk(question);
  }

  const blocked = signedIn && readyCount === 0;

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-canvas">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line px-5">
        <p className="truncate text-[13px] text-ink">{title}</p>
        {!signedIn ? (
          <span className="shrink-0 rounded-full bg-pale-yellow-bg px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.06em] text-pale-yellow-ink">
            Sample library
          </span>
        ) : null}
        <span className="ml-auto shrink-0 font-mono text-[11px] text-faint">
          {sourceCount > 0 ? `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}` : ""}
        </span>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-7">
        <div className="mx-auto max-w-[68ch] space-y-7">
          {messages.map((message) => (
            <MessageBlock key={message.id} message={message} />
          ))}

          {pending ? (
            <div className="flex items-center gap-2 text-[13px] text-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-faint" />
              Searching your library and writing an answer
            </div>
          ) : null}

          {error ? (
            <div className="rounded-[8px] border border-pale-red-ink/30 bg-pale-red-bg px-4 py-3">
              <p className="text-[13px] leading-relaxed text-pale-red-ink">{error}</p>
              <div className="mt-2.5 flex gap-3">
                <button
                  type="button"
                  onClick={onDismissError}
                  className="text-[12px] text-pale-red-ink underline underline-offset-4 opacity-70 hover:opacity-100"
                >
                  Dismiss
                </button>
                {signedIn ? (
                  <button
                    type="button"
                    onClick={() => onAsk(draft.trim() || "Try that again")}
                    className="text-[12px] text-pale-red-ink underline underline-offset-4 hover:font-medium"
                  >
                    Ask again
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}

          {blocked && messages.length === 0 && !error ? (
            <div className="rounded-[8px] border border-line bg-surface px-4 py-3">
              <p className="text-[13px] leading-relaxed text-muted">
                Nothing is searchable yet. Upload a document on the right, wait for it
                to reach <span className="text-ink">Ready</span>, then ask.
              </p>
            </div>
          ) : null}
        </div>
      </div>

      <div className="shrink-0 border-t border-line bg-canvas px-5 py-4">
        <div className="mx-auto max-w-[68ch]">
          {!signedIn ? (
            <div className="mb-3 flex flex-wrap items-center gap-2 text-[12px] text-faint">
              <span>Asking a question needs an account.</span>
              <button
                type="button"
                onClick={() => setAuthOpen(true)}
                className="text-ink underline underline-offset-4"
              >
                Sign in
              </button>
            </div>
          ) : null}

          <form
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
            className="flex items-end gap-2.5"
          >
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              rows={1}
              placeholder={
                signedIn
                  ? "Ask something your documents answer"
                  : "Sign in to ask your own documents"
              }
              className="max-h-40 min-h-11 flex-1 resize-none rounded-[6px] border border-line bg-surface px-3.5 py-3 text-[14px] leading-relaxed text-ink outline-none transition-colors placeholder:text-faint focus:border-ink"
            />
            <Button type="submit" disabled={!draft.trim() || pending} aria-label="Send">
              <Send size={15} />
            </Button>
          </form>
        </div>
      </div>

      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        reason={ASK_REASON}
        next="/chat"
      />
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

      {message.refused ? (
        <p className="mt-3 text-[12px] text-faint">
          Nothing in your library answered that, so nothing was invented.
        </p>
      ) : null}

      {message.uncited ? (
        <p className="mt-3 text-[12px] text-pale-yellow-ink">
          The answer came back without citing a source, so treat it as unverified.
        </p>
      ) : null}

      {message.citations.length > 0 ? (
        <div className="mt-5 flex flex-wrap gap-2">
          {message.citations.map((citation) => (
            <div
              key={citation.label}
              className="max-w-[46ch] rounded-[8px] border border-line bg-surface p-3"
            >
              <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-pale-blue-ink">
                {citation.label} &middot; {citation.filename} &middot;{" "}
                {citation.page > 0 ? `p. ${citation.page}` : "no page"}
              </p>
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{citation.snippet}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function HistoryColumn({
  signedIn,
  sessions,
  activeId,
  onSelect,
  onNew,
}: {
  signedIn: boolean;
  sessions: ChatSession[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
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
              onClick={() => onSelect(session.id)}
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

        {signedIn && sessions.length === 0 ? (
          <p className="px-3 py-3 text-[12px] leading-relaxed text-faint">
            Your conversations appear here once you ask something.
          </p>
        ) : null}
      </div>

      <div className="shrink-0 border-t border-line p-3">
        {signedIn ? (
          <button
            type="button"
            onClick={onNew}
            className="flex w-full items-center justify-center gap-2 rounded-[6px] border border-line px-3 py-2 text-[13px] text-ink transition-colors hover:border-line-strong hover:bg-sunk"
          >
            <Plus size={14} />
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

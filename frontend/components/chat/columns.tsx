"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { AuthModal } from "@/components/auth-modal";
import { Plus, Send } from "@/components/icons";
import { Badge, Button, SectionLabel } from "@/components/ui";
import type { ChatSession, Message } from "@/lib/types";
import { splitMarkers } from "@/lib/markers";

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
    <section className="flex min-w-0 flex-1 flex-col bg-paper">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line px-5">
        <p className="truncate text-[13px] text-ink">{title}</p>
        {!signedIn ? <Badge tone="warning">Sample library</Badge> : null}
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
            <div className="rounded-none border border-danger/40 bg-danger/10 px-4 py-3">
              <p className="text-[13px] leading-relaxed text-danger">{error}</p>
              <div className="mt-2.5 flex gap-3">
                <button
                  type="button"
                  onClick={onDismissError}
                  className="text-[12px] text-danger underline underline-offset-4"
                >
                  Dismiss
                </button>
                <button
                  type="button"
                  onClick={() => onAsk(draft.trim() || "Try that again")}
                  className="text-[12px] text-danger underline underline-offset-4"
                >
                  Ask again
                </button>
              </div>
            </div>
          ) : null}

          {blocked && messages.length === 0 && !error ? (
            <div className="rounded-none border border-warning/40 bg-warning/10 px-4 py-3">
              <p className="text-[13px] leading-relaxed text-warning">
                Nothing is searchable yet. Upload a document, wait for it to reach{" "}
                <span className="text-ink">Ready</span>, then ask.
              </p>
            </div>
          ) : null}
        </div>
      </div>

      <div className="shrink-0 border-t border-line bg-paper px-5 py-4">
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
              className="max-h-40 min-h-11 flex-1 resize-none rounded-none border border-line bg-surface px-3.5 py-3 text-[14px] leading-relaxed text-ink transition-colors placeholder:text-faint focus:border-accent"
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
  const [openSource, setOpenSource] = useState<string | null>(null);

  function toggleSource(label: string) {
    setOpenSource((current) => (current === label ? null : label));
  }

  function renderRichText(text: string) {
    const nodes: React.ReactNode[] = [];
    const paragraphs = text.split("\n\n");

    for (let pi = 0; pi < paragraphs.length; pi++) {
      const paragraph = paragraphs[pi];
      if (paragraph.startsWith("- ") || paragraph.startsWith("* ") || /^\d+\./.test(paragraph)) {
        const items: React.ReactNode[] = [];
        const lines = paragraph.split("\n");
        for (let li = 0; li < lines.length; li++) {
          const line = lines[li].replace(/^[-*]\s+|\d+\.\s+/, "");
          items.push(
            <li key={li} className="ml-4 my-1">
              {renderInline(line)}
            </li>
          );
        }
        nodes.push(<ul key={`list-${pi}`} className="ml-2 my-2 space-y-1 list-disc">{items}</ul>);
      } else {
        nodes.push(
          <p key={`para-${pi}`} className="max-w-[68ch]">
            {renderInline(paragraph)}
          </p>
        );
      }
    }
    return nodes;
  }

  function renderInline(text: string): React.ReactNode[] {
    const segments = splitMarkers(text);
    const nodes: React.ReactNode[] = [];

    for (const segment of segments) {
      if (segment.kind === "text") {
        const parts = segment.value.split(/(\*\*.+?\*\*|\*.+?\*|`.+?`)/);
        for (const part of parts) {
          if (part.startsWith("**") && part.endsWith("**")) {
            nodes.push(<strong key={`b-${nodes.length}`}>{part.slice(2, -2)}</strong>);
          } else if (part.startsWith("*") && part.endsWith("*") && !part.startsWith("**")) {
            nodes.push(<em key={`i-${nodes.length}`}>{part.slice(1, -1)}</em>);
          } else if (part.startsWith("`") && part.endsWith("`")) {
            nodes.push(<code key={`c-${nodes.length}`} className="font-mono text-[13px] bg-sunk px-1 rounded-none">{part.slice(1, -1)}</code>);
          } else {
            nodes.push(<span key={`t-${nodes.length}`}>{part}</span>);
          }
        }
      } else {
        const label = segment.label;
        const interactive = message.citations.some((c) => c.label === label);
        nodes.push(
          <sup key={`marker-${nodes.length}`} className="mx-1 font-mono text-ink">
            {interactive ? (
              <button
                type="button"
                aria-label={`Source ${label}`}
                onClick={() => {
                  toggleSource(label);
                  document.getElementById(`source-${message.id}-${label}`)?.scrollIntoView({ block: "nearest", behavior: "auto" });
                }}
                className="text-[11px] leading-none text-ink hover:text-accent transition-colors"
              >
                {label}
              </button>
            ) : (
              <span className="text-[11px] leading-none text-ink">{label}</span>
            )}
          </sup>
        );
      }
    }
    return nodes;
  }

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[52ch] rounded-none bg-sunk px-4 py-2.5 text-[14px] leading-relaxed text-ink">
          {message.content}
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="space-y-4 text-[14px] font-[family-name:var(--font-sans)] leading-relaxed text-ink-soft">
        {renderRichText(message.content)}
      </div>

      {message.refused ? (
        <p className="mt-3 text-[12px] text-faint">
          Nothing in your library answered that, so nothing was invented.
        </p>
      ) : null}

      {message.uncited ? (
        <p className="mt-3 text-[12px] text-warning">
          The answer came back without citing a source, so treat it as unverified.
        </p>
      ) : null}

      {message.citations.length > 0 ? (
        <div className="mt-5 space-y-1">
          {message.citations.map((citation) => (
            <div key={citation.label}>
              <button
                type="button"
                id={`source-${message.id}-${citation.label}`}
                aria-expanded={openSource === citation.label}
                onClick={() => toggleSource(citation.label)}
                className="flex w-full items-baseline gap-2 text-left text-[13px] text-ink-soft"
              >
                <span className="font-mono">{citation.label}</span>
                <span className="min-w-0 break-words">{citation.filename}</span>
                <span className="shrink-0 text-muted">
                  {citation.page > 0 ? `p. ${citation.page}` : "no page"}
                </span>
              </button>
              {openSource === citation.label ? (
                <p className="mt-1 text-[12px] leading-relaxed text-muted">{citation.snippet}</p>
              ) : null}
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
        <SectionLabel>Contents</SectionLabel>
      </div>

      <div className="flex-1 overflow-y-auto px-2.5 pb-4">
        {sessions.map((session) => {
          const active = session.id === activeId;
          return (
            <button
              key={session.id}
              type="button"
              onClick={() => onSelect(session.id)}
              className={`mb-0.5 w-full rounded-none border border-transparent px-3 py-2.5 text-left transition-colors ${
                active ? "border-l-accent bg-sunk" : "hover:bg-sunk/60"
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
            className="flex w-full items-center justify-center gap-2 rounded-none border border-line px-3 py-2 text-[13px] text-ink transition-colors hover:border-line-strong hover:bg-sunk"
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

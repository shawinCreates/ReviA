"use client";

import { useMemo } from "react";

import { ChatColumn, HistoryColumn } from "@/components/chat/columns";
import { LibraryColumn } from "@/components/chat/library-column";
import { useChat } from "@/lib/use-chat";
import { useLibrary } from "@/lib/use-library";
import { DEMO_DOCUMENTS, DEMO_MESSAGES, DEMO_SESSIONS } from "@/lib/mock/data";
import type { ChatSession, LibraryDocument, Message } from "@/lib/types";

type Props = {
  signedIn: boolean;
  libraryId: string | null;
  initialDocuments: LibraryDocument[];
  initialSessions: ChatSession[];
  initialMessages: Message[];
  initialSessionId: string | null;
};

/**
 * Owns the state the three columns share, so the library and the transcript
 * cannot disagree about what is in the library. The columns stay presentational
 * and hold no fetching of their own.
 */
export function ChatWorkspace({
  signedIn,
  libraryId,
  initialDocuments,
  initialSessions,
  initialMessages,
  initialSessionId,
}: Props) {
  const library = useLibrary({
    signedIn,
    initial: initialDocuments,
    fallback: DEMO_DOCUMENTS,
    libraryId,
  });

  const chat = useChat({
    signedIn,
    initialSessions,
    initialMessages,
    initialSessionId,
    libraryId,
    fallbackSessions: DEMO_SESSIONS,
    fallbackMessages: DEMO_MESSAGES,
  });

  // A library with nothing searchable is a different screen from one that can
  // answer, and finding that out by asking an empty library is a bad first run.
  const readyCount = useMemo(
    () => library.documents.filter((entry) => entry.status === "ready").length,
    [library.documents],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <HistoryColumn
        signedIn={signedIn}
        sessions={chat.sessions}
        activeId={chat.activeId}
        onSelect={chat.selectSession}
        onNew={chat.newConversation}
      />
      <ChatColumn
        signedIn={signedIn}
        messages={chat.messages}
        pending={chat.pending}
        error={chat.error}
        onAsk={chat.ask}
        onDismissError={chat.dismissError}
        readyCount={readyCount}
      />
      <LibraryColumn
        signedIn={signedIn}
        documents={library.documents}
        uploading={library.uploading}
        deletingId={library.deletingId}
        error={library.error}
        onUpload={library.upload}
        onRemove={library.remove}
        onDismissError={library.dismissError}
      />
    </div>
  );
}

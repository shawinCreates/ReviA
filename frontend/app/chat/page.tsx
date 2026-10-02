import { Suspense } from "react";

import { AppHeader } from "@/components/app-header";
import { ChatWorkspace } from "@/components/chat/workspace";
import { getUser } from "@/lib/auth";
import { loadDocuments, loadLibraries, loadSessionMessages, loadSessions } from "@/lib/api-server";

export const metadata = { title: "Chat" };

export default async function ChatPage() {
  const user = await getUser();
  const signedIn = Boolean(user);

  // Loaded on the server so the transcript and the library are already on
  // screen at first paint. A signed-out visitor skips all three: they would be
  // unauthorised, and the sample library is not the API's to ask about.
  const [libraries, documents, sessions] = signedIn
    ? await Promise.all([loadLibraries(), loadDocuments(), loadSessions()])
    : [[], [], []];

  const libraryId = libraries.find((library) => library.is_default)?.id ?? null;

  // Opening the newest conversation rather than an empty composer: a returning
  // user coming back to the chat expects to find the thread they left.
  const initialSessionId = sessions[0]?.id ?? null;
  const initialMessages = initialSessionId ? await loadSessionMessages(initialSessionId) : [];

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <AppHeader />
      <Suspense fallback={<div className="flex-1 bg-paper" />}>
        <ChatWorkspace
          signedIn={signedIn}
          libraryId={libraryId}
          initialDocuments={documents}
          initialSessions={sessions}
          initialMessages={initialMessages}
          initialSessionId={initialSessionId}
        />
      </Suspense>
    </div>
  );
}

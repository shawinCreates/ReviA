import { Suspense } from "react";

import { AppHeader } from "@/components/app-header";
import { ChatWorkspace } from "@/components/chat/workspace";
import { HealthGate } from "@/components/health-status";
import { getUser } from "@/lib/auth";
import { pingApi } from "@/lib/api";
import { loadDocuments, loadLibraries, loadSessionMessages, loadSessions } from "@/lib/api-server";

export const metadata = { title: "Chat" };

export default async function ChatPage() {
  if (!(await pingApi())) return <HealthGate path="/chat" />;

  const user = await getUser();
  const signedIn = Boolean(user);

  const [libraries, documents, sessions] = signedIn
    ? await Promise.all([loadLibraries(), loadDocuments(), loadSessions()])
    : [[], [], []];

  const libraryId = libraries.find((library) => library.is_default)?.id ?? null;

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

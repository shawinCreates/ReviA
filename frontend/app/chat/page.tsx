import { Suspense } from "react";

import { AppHeader } from "@/components/app-header";
import { ChatWorkspace } from "@/components/chat/workspace";
import { getUser } from "@/lib/auth";

export const metadata = { title: "Chat" };

export default async function ChatPage() {
  const user = await getUser();

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <AppHeader />
      <Suspense fallback={<div className="flex-1 bg-canvas" />}>
        <ChatWorkspace signedIn={Boolean(user)} />
      </Suspense>
    </div>
  );
}

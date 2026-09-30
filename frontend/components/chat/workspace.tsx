"use client";

import { ChatColumn, HistoryColumn } from "@/components/chat/columns";
import { LibraryColumn } from "@/components/chat/library-column";

export function ChatWorkspace({ signedIn }: { signedIn: boolean }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <HistoryColumn signedIn={signedIn} />
      <ChatColumn signedIn={signedIn} />
      <LibraryColumn signedIn={signedIn} />
    </div>
  );
}

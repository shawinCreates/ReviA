import Link from "next/link";
import { Suspense } from "react";

import { AppHeader } from "@/components/app-header";
import { PipelineBoard } from "@/components/pipeline/board";
import { getUser } from "@/lib/auth";

export const metadata = { title: "Ingestion pipeline" };

export default async function PipelinePage() {
  const user = await getUser();

  return (
    <div className="flex min-h-dvh flex-col">
      <AppHeader />
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
                Ingestion
              </p>
              <h1 className="mt-3 max-w-[20ch] text-title">
                Every document, and the stage it is in.
              </h1>
              <p className="mt-4 max-w-[56ch] text-[15px] leading-relaxed text-ink-soft">
                Uploading a folder of lecture slides is normal, not an edge case. Each
                file reports its own stage and progress, and a failure says what
                failed rather than retrying quietly.
              </p>
            </div>
            <Link
              href="/chat"
              className="text-[13px] text-muted underline underline-offset-4 hover:text-ink"
            >
              Back to chat
            </Link>
          </div>

          <Suspense fallback={<div className="mt-14 h-64 bg-sunk" />}>
            <PipelineBoard signedIn={Boolean(user)} />
          </Suspense>
        </div>
      </main>
    </div>
  );
}

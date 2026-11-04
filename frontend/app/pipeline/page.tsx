import Link from "next/link";
import { Suspense } from "react";

import { AppHeader } from "@/components/app-header";
import { PipelineBoard } from "@/components/pipeline/board";
import { HealthGate } from "@/components/health-status";
import { getUser } from "@/lib/auth";
import { pingApi } from "@/lib/api";
import { loadDocuments } from "@/lib/api-server";
import { STAGES } from "@/lib/config";

export const metadata = {
  title: "Ingestion pipeline",
  description:
    "Watch your uploads move through queued, parsing, chunking, embedding and ready, with a stage and progress for every document.",
  robots: { index: false, follow: true },
  alternates: { canonical: "/pipeline" },
};

export default async function PipelinePage() {
  if (!(await pingApi())) return <HealthGate path="/pipeline" />;

  const user = await getUser();
  const signedIn = Boolean(user);
  const documents = user ? await loadDocuments() : [];

  return (
    <div className="flex min-h-dvh flex-col" id="main" tabIndex={-1}>
      <AppHeader />
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-faint">
                <span className="block">Ingestion</span>
                <span className="block">{STAGES.length} stages</span>
              </p>
              <h1 className="mt-4 max-w-[20ch] font-[family-name:var(--font-display)] text-[1.75rem] leading-[1.12] tracking-[-0.02em] md:text-[2.25rem]">
                Every document, and the stage it is in.
              </h1>
              <p className="mt-5 max-w-[56ch] text-[15px] leading-relaxed text-ink-soft">
                Uploading a folder of lecture slides is normal, not an edge case. Each
                file reports its own stage and progress, and a failure says what
                failed rather than retrying quietly.
              </p>
            </div>
            <Link
              href="/chat"
              className="inline-flex items-center border border-line px-3.5 py-2 text-[13px] text-muted transition-colors duration-200 hover:border-ink hover:text-ink motion-reduce:transition-none"
            >
              Back to chat
            </Link>
          </div>

          <Suspense
            fallback={
              <div
                className={`${signedIn ? "mt-14" : "mt-12"} h-72 border border-line bg-paper`}
              />
            }
          >
            <PipelineBoard signedIn={signedIn} initialDocuments={documents} />
          </Suspense>
        </div>
      </main>
    </div>
  );
}

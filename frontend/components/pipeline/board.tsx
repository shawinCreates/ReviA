import Link from "next/link";

import { DEMO_DOCUMENTS, PIPELINE_DOCUMENTS, documentsByStage } from "@/lib/mock/data";
import { STAGES, STAGE_LABELS } from "@/lib/config";
import type { LibraryDocument } from "@/lib/types";
import { Alert, Check, FileText } from "@/components/icons";
import { ButtonLink } from "@/components/ui";

const BLURB = {
  queued: "Accepted and waiting for a worker",
  parsing: "Reading text and page structure",
  chunking: "Slicing pages into retrievable chunks",
  embedding: "Writing vectors and the search index",
  ready: "Searchable, and answering questions",
  failed: "Stopped, with the reason given",
} as const;

export function PipelineBoard({ signedIn = false }: { signedIn?: boolean }) {
  const documents = signedIn ? PIPELINE_DOCUMENTS : DEMO_DOCUMENTS;
  const grouped = documentsByStage(documents);
  const active = documents.filter((document) => document.status !== "ready").length;

  return (
    <div className={signedIn ? "mt-14" : "mt-12"}>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <p className="text-[13px] text-ink-soft">
          <span className="font-mono text-ink">{active}</span> in flight
        </p>
        <p className="text-[13px] text-muted">
          <span className="font-mono text-ink-soft">{documents.length}</span> documents
        </p>
        {!signedIn ? (
          <p className="text-[13px] text-muted">Showing the sample library</p>
        ) : null}
      </div>

      <div className="mt-6 grid gap-px overflow-hidden rounded-[10px] border border-line bg-line sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {STAGES.map((stage) => {
          const entries = grouped[stage];
          return (
            <section key={stage} className="flex min-h-[220px] flex-col bg-canvas">
              <div className="border-b border-line px-4 py-3.5">
                <div className="flex items-center gap-2">
                  <StageDot stage={stage} />
                  <p className="text-[13px] text-ink">{STAGE_LABELS[stage]}</p>
                  <span className="ml-auto font-mono text-[11px] text-faint">{entries.length}</span>
                </div>
                <p className="mt-1.5 text-[11px] leading-relaxed text-faint">{BLURB[stage]}</p>
              </div>

              <div className="flex-1 space-y-1.5 p-2">
                {entries.length === 0 ? (
                  <p className="px-2 py-3 text-[12px] text-faint">Empty</p>
                ) : (
                  entries.map((document) => <Card key={document.id} document={document} />)
                )}
              </div>
            </section>
          );
        })}
      </div>

      {!signedIn ? (
        <div className="mt-8 flex flex-wrap items-center justify-between gap-5 rounded-[10px] border border-line bg-surface px-6 py-6">
          <p className="max-w-[48ch] text-[14px] leading-relaxed text-ink-soft">
            This board shows the sample library. Sign in and it tracks your own
            uploads, including the ones still in the queue.
          </p>
          <ButtonLink href="/login?mode=signup" size="sm">
            Create an account
          </ButtonLink>
        </div>
      ) : null}
    </div>
  );
}

function StageDot({ stage }: { stage: (typeof STAGES)[number] }) {
  if (stage === "ready") return <Check size={13} className="text-pale-green-ink" />;
  if (stage === "failed") return <Alert size={13} className="text-pale-red-ink" />;
  return <span className="h-1.5 w-1.5 rounded-full bg-line-strong" />;
}

function Card({ document }: { document: LibraryDocument }) {
  return (
    <Link
      href="/chat"
      className="block rounded-[7px] border border-line bg-surface p-3 transition-shadow hover:shadow-whisper"
    >
      <div className="flex items-start gap-2">
        <FileText size={13} className="mt-0.5 shrink-0 text-faint" />
        <p className="line-clamp-2 text-[12px] leading-snug text-ink-soft">{document.filename}</p>
      </div>
      <p className="mt-2 pl-[21px] font-mono text-[10px] leading-relaxed text-faint">
        {document.stageDetail}
      </p>
      {document.error ? (
        <p className="mt-2 rounded-[5px] bg-pale-red-bg px-2 py-1.5 text-[10px] leading-relaxed text-pale-red-ink">
          {document.error}
        </p>
      ) : null}
    </Link>
  );
}

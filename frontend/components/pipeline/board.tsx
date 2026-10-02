"use client";

import Link from "next/link";
import { useMemo } from "react";

import { STAGES, STAGE_BLURBS, STAGE_LABELS } from "@/lib/config";
import { DEMO_PIPELINE_DOCUMENTS, documentsByStage } from "@/lib/mock/data";
import type { LibraryDocument } from "@/lib/types";
import { useLibrary } from "@/lib/use-library";
import { Alert, Check, FileText } from "@/components/icons";
import { ButtonLink } from "@/components/ui";

const IN_FLIGHT = new Set(["queued", "parsing", "chunking", "embedding"]);

export function PipelineBoard({
  signedIn = false,
  initialDocuments = [],
}: {
  signedIn?: boolean;
  initialDocuments?: LibraryDocument[];
}) {
  // The board is a live view of the same library the chat column reads, so it
  // uses the same hook rather than a second, divergent copy of the pipeline.
  const library = useLibrary({
    signedIn,
    initial: initialDocuments,
    fallback: DEMO_PIPELINE_DOCUMENTS,
  });

  const documents = library.documents;
  const grouped = useMemo(() => documentsByStage(documents), [documents]);
  const active = documents.filter((entry) => IN_FLIGHT.has(entry.status)).length;

  return (
    <div className={signedIn ? "mt-14" : "mt-12"}>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 border-b border-line pb-3">
        <p className="text-[13px] text-ink-soft">
          <span className="font-mono text-ink">{active}</span> in flight
        </p>
        <p className="text-[13px] text-muted">
          <span className="font-mono text-ink-soft">{documents.length}</span> documents
        </p>
        {!signedIn ? (
          <p className="text-[12px] text-muted">Showing the sample library</p>
        ) : null}
      </div>

      {library.error ? (
        <p className="mt-4 border border-danger/40 bg-danger/10 px-4 py-2.5 text-[12px] leading-relaxed text-danger">
          {library.error}
        </p>
      ) : null}

      {/* Hairline rails: the border is drawn on the cells rather than as a
          gap-px background, so the grid stays square at every breakpoint and
          does not need `overflow-hidden` to clip its corners. */}
      <div className="mt-6 grid grid-cols-1 border-l border-t border-line sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {STAGES.map((stage) => {
          const entries = grouped[stage];
          const moving = entries.some((entry) => IN_FLIGHT.has(entry.status));
          return (
            <section
              key={stage}
              className="flex min-h-[220px] flex-col border-b border-r border-line bg-paper"
            >
              <div className="border-b border-line px-4 py-3.5">
                <div className="flex items-center gap-2">
                  <StageGlyph stage={stage} />
                  {/* A real heading per rail, so a screen reader can jump
                      stage to stage instead of reading six columns of prose. */}
                  <h2 className="text-[13px] font-normal text-ink">{STAGE_LABELS[stage]}</h2>
                  <span
                    className={`ml-auto font-mono text-[11px] ${moving ? "text-accent" : "text-faint"}`}
                  >
                    {entries.length}
                  </span>
                </div>
                <p className="mt-1.5 text-[11px] leading-relaxed text-faint">{STAGE_BLURBS[stage]}</p>
              </div>

              <div className="flex-1 space-y-1.5 p-2">
                {entries.length === 0 ? (
                  <p className="px-2 py-3 text-[12px] text-faint">Nothing at this stage</p>
                ) : (
                  entries.map((document) => <Card key={document.id} document={document} />)
                )}
              </div>
            </section>
          );
        })}
      </div>

      {!signedIn ? (
        <div className="mt-8 flex flex-wrap items-center justify-between gap-5 border border-line border-l-2 border-l-accent bg-surface px-6 py-6">
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

/** One glyph per rail: a verdict where the stage is a verdict, a dot otherwise. */
function StageGlyph({ stage }: { stage: (typeof STAGES)[number] }) {
  if (stage === "ready") return <Check size={13} className="text-success" />;
  if (stage === "failed") return <Alert size={13} className="text-danger" />;
  return <span className="h-1.5 w-1.5 rounded-full bg-line-strong" />;
}

function Card({ document }: { document: LibraryDocument }) {
  return (
    <Link
      href="/chat"
      className="block border border-line bg-surface p-3 transition-colors duration-200 hover:border-line-strong hover:bg-sunk active:bg-line motion-reduce:transition-none"
    >
      <div className="flex items-start gap-2">
        <FileText size={13} className="mt-0.5 shrink-0 text-faint" />
        {/* `min-w-0 break-words` so a long unbreakable filename wraps inside the
            card instead of widening the flex item and the page with it. */}
        <p className="line-clamp-2 min-w-0 break-words text-[12px] leading-snug text-ink-soft">
          {document.filename}
        </p>
      </div>
      <p className="mt-2 pl-[21px] font-mono text-[10px] leading-relaxed text-faint">
        {document.stageDetail}
      </p>
      {document.error ? (
        <p className="mt-2 flex items-start gap-1.5 border border-danger/30 bg-danger/10 px-2 py-1.5 text-[10px] leading-relaxed text-danger">
          <Alert size={11} className="mt-[1px] shrink-0" />
          {document.error}
        </p>
      ) : null}
    </Link>
  );
}

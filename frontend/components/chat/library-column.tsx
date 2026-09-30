"use client";

import { useRef, useState } from "react";

import { AuthModal, UPLOAD_REASON } from "@/components/auth-modal";
import { FileText, Trash, Upload } from "@/components/icons";
import { DEMO_DOCUMENTS } from "@/lib/mock/data";
import { MAX_UPLOAD_BYTES, STAGE_LABELS } from "@/lib/config";
import type { LibraryDocument } from "@/lib/types";
import { Badge, Button, ButtonLink } from "@/components/ui";

const TONES = {
  queued: "neutral",
  parsing: "blue",
  chunking: "blue",
  embedding: "yellow",
  ready: "green",
  failed: "red",
} as const;

function megabytes(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function LibraryColumn({ signedIn }: { signedIn: boolean }) {
  const [documents, setDocuments] = useState<LibraryDocument[]>(DEMO_DOCUMENTS);
  const [authOpen, setAuthOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  function openPicker() {
    if (signedIn) inputRef.current?.click();
    else setAuthOpen(true);
  }

  function onFiles(files: FileList | null) {
    if (!files || !signedIn) return;

    const incoming = Array.from(files).map<LibraryDocument>((file) => ({
      id: `local-${file.name}-${file.size}`,
      filename: file.name,
      sizeBytes: file.size,
      pageCount: null,
      status: "queued",
      stageDetail: "Waiting for a worker",
      error: null,
      createdAt: new Date().toISOString(),
      owned: true,
    }));

    setDocuments((current) => [...incoming, ...current]);
  }

  return (
    <aside className="flex w-full shrink-0 flex-col border-t border-line bg-surface lg:w-[320px] lg:border-t-0 lg:border-l">
      <div className="flex h-11 shrink-0 items-center px-5">
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-faint">Library</p>
        <span className="ml-auto font-mono text-[10px] text-faint">
          {documents.length} of 20
        </span>
      </div>

      <div className="px-4 pb-4">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.pptx"
          className="hidden"
          onChange={(event) => onFiles(event.target.files)}
        />

        <div
          onDragOver={(event) => {
            event.preventDefault();
            if (signedIn) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            onFiles(event.dataTransfer.files);
          }}
          onClick={openPicker}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              openPicker();
            }
          }}
          className={`cursor-pointer rounded-[10px] border border-dashed px-4 py-6 text-center transition-colors ${
            dragging ? "border-ink bg-sunk" : "border-line-strong hover:border-ink hover:bg-sunk/50"
          }`}
        >
          <Upload size={18} className="mx-auto text-muted" />
          <p className="mt-2.5 text-[13px] text-ink">
            {signedIn ? "Drop files or click to upload" : "Sign in to upload your own"}
          </p>
          <p className="mt-1 text-[11px] text-faint">
            PDF, DOCX, PPTX &middot; up to {megabytes(MAX_UPLOAD_BYTES)}
          </p>
        </div>

        {!signedIn ? (
          <ButtonLink
            href="/login?mode=signup"
            variant="outline"
            size="sm"
            className="mt-3 w-full"
          >
            Create a free account
          </ButtonLink>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto border-t border-line px-2.5 py-3">
        {documents.map((document) => (
          <div
            key={document.id}
            className="group mb-1 rounded-[6px] px-3 py-2.5 transition-colors hover:bg-sunk/60"
          >
            <div className="flex items-start gap-2.5">
              <FileText size={15} className="mt-0.5 shrink-0 text-faint" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] text-ink-soft">{document.filename}</p>
                <p className="mt-1 flex items-center gap-2 font-mono text-[10px] text-faint">
                  <span>{megabytes(document.sizeBytes)}</span>
                  {document.pageCount ? <span>{document.pageCount} pages</span> : null}
                </p>
              </div>
              {document.owned ? (
                <button
                  type="button"
                  aria-label={`Delete ${document.filename}`}
                  onClick={() =>
                    setDocuments((current) =>
                      current.filter((entry) => entry.id !== document.id),
                    )
                  }
                  className="shrink-0 text-faint opacity-0 transition-opacity hover:text-pale-red-ink group-hover:opacity-100"
                >
                  <Trash size={14} />
                </button>
              ) : null}
            </div>

            <div className="mt-2 flex items-center gap-2 pl-[25px]">
              <Badge tone={TONES[document.status]}>{STAGE_LABELS[document.status]}</Badge>
              <span className="truncate text-[11px] text-faint">{document.stageDetail}</span>
            </div>

            {document.error ? (
              <p className="mt-2 rounded-[5px] bg-pale-red-bg px-2.5 py-1.5 pl-[35px] text-[11px] leading-relaxed text-pale-red-ink">
                {document.error}
              </p>
            ) : null}
          </div>
        ))}
      </div>

      <div className="shrink-0 border-t border-line px-4 py-3">
        <Button variant="ghost" size="sm" className="w-full" onClick={openPicker}>
          <Upload size={14} />
          {signedIn ? "Upload documents" : "Sign in to upload"}
        </Button>
      </div>

      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        reason={UPLOAD_REASON}
        next="/chat"
      />
    </aside>
  );
}

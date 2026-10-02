"use client";

import { useRef, useState } from "react";

import { AuthModal, UPLOAD_REASON } from "@/components/auth-modal";
import { FileText, Trash, Upload } from "@/components/icons";
import { MAX_UPLOAD_BYTES, STAGE_LABELS, SUPPORTED_UPLOAD_EXTENSIONS } from "@/lib/config";
import type { LibraryDocument } from "@/lib/types";
import { Badge, Button, ButtonLink, SectionLabel } from "@/components/ui";

const TONES = {
  queued: "neutral",
  parsing: "accent",
  chunking: "accent",
  embedding: "warning",
  ready: "success",
  failed: "danger",
} as const;

function megabytes(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function LibraryColumn({
  signedIn,
  documents,
  uploading,
  deletingId,
  error,
  onUpload,
  onRemove,
  onDismissError,
}: {
  signedIn: boolean;
  documents: LibraryDocument[];
  uploading: string[];
  deletingId: string | null;
  error: string | null;
  onUpload: (files: File[]) => void;
  onRemove: (id: string) => void;
  onDismissError: () => void;
}) {
  const [authOpen, setAuthOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  function openPicker() {
    if (signedIn) inputRef.current?.click();
    else setAuthOpen(true);
  }

  function onFiles(files: FileList | null) {
    if (!files || !signedIn) return;

    const incoming = Array.from(files);

    // Rejected here rather than at the API: the same rules are enforced
    // server-side, but telling someone their 40MB scan is too large while they
    // are still looking at the file is better than after the upload finishes.
    const tooBig = incoming.find((file) => file.size > MAX_UPLOAD_BYTES);
    if (tooBig) {
      setRejected(`${tooBig.name} is ${megabytes(tooBig.size)}. The limit is ${megabytes(MAX_UPLOAD_BYTES)}.`);
      return;
    }

    const wrongType = incoming.find(
      (file) =>
        !SUPPORTED_UPLOAD_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension)),
    );
    if (wrongType) {
      setRejected(`${wrongType.name} is not a PDF, DOCX or PPTX.`);
      return;
    }

    setRejected(null);
    onUpload(incoming);
  }

  return (
    <aside className="flex w-full shrink-0 flex-col border-t border-line bg-surface lg:w-[320px] lg:border-t-0 lg:border-l">
      <div className="flex h-11 shrink-0 items-center px-5">
        <SectionLabel>Library</SectionLabel>
        <span className="ml-auto font-mono text-[10px] text-faint">{documents.length} files</span>
      </div>

      <div className="px-4 pb-4">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={SUPPORTED_UPLOAD_EXTENSIONS.join(",")}
          className="hidden"
          onChange={(event) => {
            onFiles(event.target.files);
            // Reset so re-picking the same file fires `change` again.
            event.target.value = "";
          }}
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
          className={`cursor-pointer rounded-none border border-dashed px-4 py-6 text-center transition-colors ${
            dragging ? "border-accent bg-sunk" : "border-line-strong hover:border-ink hover:bg-sunk/50"
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

        {uploading.length > 0 ? (
          <div className="mt-3 rounded-none border border-line bg-sunk px-3 py-2.5">
            <p className="flex items-center gap-2 text-[12px] text-ink-soft">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-faint" />
              Uploading {uploading.length === 1 ? uploading[0] : `${uploading.length} files`}
            </p>
            {/* An honest "in progress" rather than a fabricated percentage: the
                browser exposes no upload progress through fetch, and a bar that
                guesses is worse than one that admits it does not know. */}
          </div>
        ) : null}

        {rejected ? (
          <p className="mt-3 rounded-none bg-danger/10 px-3 py-2 text-[11px] leading-relaxed text-danger">
            {rejected}
          </p>
        ) : null}

        {error ? (
          <div className="mt-3 rounded-none bg-danger/10 px-3 py-2 text-[11px] leading-relaxed text-danger">
            <p>{error}</p>
            <button
              type="button"
              onClick={() => {
                onDismissError();
                setRejected(null);
              }}
              className="mt-1.5 text-[10px] underline underline-offset-4"
            >
              Dismiss
            </button>
          </div>
        ) : null}

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
        {documents.length === 0 ? (
          <p className="px-3 py-4 text-[12px] leading-relaxed text-faint">
            {signedIn
              ? "No documents yet. Upload a PDF, DOCX or PPTX to get started."
              : "The sample library is empty."}
          </p>
        ) : null}

        {documents.map((document) => (
          <div
            key={document.id}
            className="group mb-1 rounded-none px-3 py-2.5 transition-colors hover:bg-sunk/60"
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
                  disabled={deletingId === document.id}
                  onClick={() => onRemove(document.id)}
                  className="shrink-0 text-faint opacity-0 transition-opacity hover:text-danger focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-40"
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
              <p className="mt-2 rounded-none bg-danger/10 px-2.5 py-1.5 pl-[35px] text-[11px] leading-relaxed text-danger">
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

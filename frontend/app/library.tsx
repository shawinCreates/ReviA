"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  createDocument,
  createLibrary,
  getLibrary,
  ingestDocument,
  listLibraries,
  uploadFile,
  type DocumentSummary,
  type Library,
  type LibraryDetail,
} from "./lib/api";

/**
 * The upload flow, end to end.
 *
 * Three calls per file, and the browser drives the third in a loop until the
 * document is ready — there is no worker. The cursor lives in the database, so
 * a document left mid-ingest resumes from where it stopped when this view
 * mounts, without the user doing anything. See ingestion.md.
 *
 * Nothing here proxies file bytes through Django: the file goes straight to
 * Supabase Storage with the presigned URL returned by the API.
 */

const MIME_BY_EXT: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  md: "text/markdown",
  txt: "text/plain",
  csv: "text/csv",
};

const ACCEPT = Object.keys(MIME_BY_EXT)
  .map((ext) => `.${ext}`)
  .join(",");

const TERMINAL: ReadonlyArray<DocumentSummary["status"]> = ["ready", "failed"];

function mimeFor(filename: string): string | null {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return MIME_BY_EXT[ext] ?? null;
}

function progressLabel(doc: DocumentSummary): string {
  if (doc.status === "ready") return `Ready · ${doc.page_count ?? 0} pages`;
  if (doc.status === "failed") return doc.error ?? "Failed";
  if (doc.page_count && doc.page_count > 0) {
    const page = Math.min(doc.ingest_cursor + 1, doc.page_count);
    return `Indexing page ${page} of ${doc.page_count}`;
  }
  return "Starting…";
}

export default function LibraryView({ email }: { email: string }) {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LibraryDetail | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [working, setWorking] = useState<Record<string, string>>({});
  const fileInput = useRef<HTMLInputElement>(null);
  // Which documents this mount has already tried to resume, so a re-render
  // does not restart an ingest that is already running.
  const resumed = useRef<Set<string>>(new Set());

  const describe = useCallback(
    (err: unknown) =>
      err instanceof ApiError ? err.message : "Something went wrong.",
    [],
  );

  const refreshLibraries = useCallback(async (): Promise<Library[]> => {
    const rows = await listLibraries();
    setLibraries(rows);
    return rows;
  }, []);

  const refreshDetail = useCallback(async (libraryId: string) => {
    const next = await getLibrary(libraryId);
    setDetail(next);
    return next;
  }, []);

  /**
   * Drive ingest to completion for one document.
   *
   * Each call advances at most one batch. The loop re-reads the document after
   * each batch so the progress bar reflects real page counts; the endpoint
   * itself is idempotent, so a retry after a network blip is safe.
   */
  const runIngest = useCallback(
    async (libraryId: string, documentId: string, filename: string) => {
      setWorking((prev) => ({ ...prev, [documentId]: `${filename} · starting` }));
      try {
        for (let guard = 0; guard < 500; guard++) {
          const result = await ingestDocument(documentId);
          if (result.status === "failed") {
            setError(result.error ?? `${filename} could not be indexed.`);
            break;
          }
          if (result.done) {
            setWorking((prev) => {
              const next = { ...prev };
              delete next[documentId];
              return next;
            });
            break;
          }
          const fresh = await refreshDetail(libraryId);
          const doc = fresh.documents.find((d) => d.id === documentId);
          setWorking((prev) => ({
            ...prev,
            [documentId]: doc ? progressLabel(doc) : `${filename} · indexing`,
          }));
        }
      } catch (err) {
        setError(describe(err));
      } finally {
        setWorking((prev) => {
          const next = { ...prev };
          delete next[documentId];
          return next;
        });
        await refreshDetail(libraryId).catch(() => undefined);
        await refreshLibraries().catch(() => undefined);
      }
    },
    [describe, refreshDetail, refreshLibraries],
  );

  // Load libraries once, then select the first one.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await refreshLibraries();
        if (!cancelled && rows.length > 0) setSelectedId(rows[0].id);
      } catch (err) {
        if (!cancelled) setError(describe(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [describe, refreshLibraries]);

  // Whenever a library is selected, load it and resume anything unfinished.
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    (async () => {
      try {
        const next = await refreshDetail(selectedId);
        if (cancelled) return;
        for (const doc of next.documents) {
          if (TERMINAL.includes(doc.status)) continue;
          if (resumed.current.has(doc.id)) continue;
          resumed.current.add(doc.id);
          void runIngest(selectedId, doc.id, doc.filename);
        }
      } catch (err) {
        if (!cancelled) setError(describe(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, describe, refreshDetail, runIngest]);

  async function onCreateLibrary(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createLibrary(title.trim());
      setTitle("");
      setSelectedId(created.id);
      await refreshLibraries();
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(files: FileList | null) {
    if (!files || files.length === 0 || !selectedId) return;
    setError(null);
    for (const file of Array.from(files)) {
      const mime = mimeFor(file.name);
      if (!mime) {
        setError(`${file.name}: that file type is not supported.`);
        continue;
      }
      try {
        const created = await createDocument({
          library_id: selectedId,
          filename: file.name,
          mime,
          size_bytes: file.size,
        });
        await uploadFile(created, file);
        await refreshDetail(selectedId);
        await runIngest(selectedId, created.id, created.filename);
      } catch (err) {
        setError(describe(err));
      }
    }
    if (fileInput.current) fileInput.current.value = "";
  }

  // `detail` lags `selectedId` by a request, so ignore it once the selection
  // has moved on — otherwise switching libraries flashes the old one's files.
  const visibleDetail =
    detail && selectedId && detail.id === selectedId ? detail : null;

  const active = Object.entries(working);

  return (
    <div className="w-full max-w-2xl space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Your library</h2>
          <p className="font-mono text-xs text-zinc-500">{email}</p>
        </div>
        {libraries.length > 0 && (
          <button
            onClick={() => fileInput.current?.click()}
            className="rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383658]"
          >
            Upload document
          </button>
        )}
        <input
          ref={fileInput}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => onUpload(e.target.files)}
        />
      </header>

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </p>
      )}

      {libraries.length === 0 ? (
        <form
          onSubmit={onCreateLibrary}
          className="space-y-4 rounded-lg border border-black/[.08] bg-white p-6 dark:border-white/[.145] dark:bg-black"
        >
          <h3 className="text-base font-semibold">Create your first library</h3>
          <p className="text-sm text-zinc-500">
            A library groups related documents. Documents are uploaded into a
            library and questions are asked against it.
          </p>
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Cell biology"
            className="w-full rounded border border-black/[.15] px-3 py-2 text-sm dark:border-white/[.2] dark:bg-black"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383658] disabled:opacity-50"
          >
            {busy ? "Creating…" : "Create library"}
          </button>
        </form>
      ) : (
        <div className="space-y-4">
          {libraries.length > 1 && (
            <select
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(e.target.value)}
              className="w-full rounded border border-black/[.15] px-3 py-2 text-sm dark:border-white/[.2] dark:bg-black"
            >
              {libraries.map((lib) => (
                <option key={lib.id} value={lib.id}>
                  {lib.title}
                </option>
              ))}
            </select>
          )}

          <DocumentList detail={visibleDetail} working={working} />

          {active.length > 0 && (
            <p className="text-xs text-zinc-500">
              {active.length} document{active.length > 1 ? "s" : ""} in
              progress. You can leave this page; indexing resumes when you
              return.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function DocumentList({
  detail,
  working,
}: {
  detail: LibraryDetail | null;
  working: Record<string, string>;
}) {
  if (!detail) {
    return <p className="text-sm text-zinc-500">Loading…</p>;
  }
  if (detail.documents.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-black/[.15] px-4 py-10 text-center text-sm text-zinc-500 dark:border-white/[.2]">
        No documents yet. Upload a PDF, Word, PowerPoint, Excel, Markdown, or
        text file.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-black/[.06] rounded-lg border border-black/[.08] bg-white dark:divide-white/[.08] dark:border-white/[.145] dark:bg-black">
      {detail.documents.map((doc) => {
        const label = working[doc.id] ?? progressLabel(doc);
        const pending = !TERMINAL.includes(doc.status);
        return (
          <li key={doc.id} className="space-y-1 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="truncate text-sm font-medium">
                {doc.filename}
              </span>
              <StatusBadge status={doc.status} />
            </div>
            <p
              className={
                "text-xs " +
                (doc.status === "failed" ? "text-red-600" : "text-zinc-500")
              }
            >
              {label}
            </p>
            {pending && doc.page_count ? (
              <div className="h-1 w-full overflow-hidden rounded-full bg-black/[.06] dark:bg-white/[.1]">
                <div
                  className="h-full rounded-full bg-foreground transition-all"
                  style={{
                    width: `${Math.min(
                      100,
                      Math.round((doc.ingest_cursor / doc.page_count) * 100),
                    )}%`,
                  }}
                />
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function StatusBadge({ status }: { status: DocumentSummary["status"] }) {
  const styles: Record<DocumentSummary["status"], string> = {
    ready: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
    queued: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
    parsing: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    indexing: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  };
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${styles[status]}`}
    >
      {status}
    </span>
  );
}

/**
 * Document state: the one place the library column and the pipeline board agree
 * on what the library contains.
 *
 * Polling exists because ingestion is asynchronous. A worker picks the document
 * up seconds later, and the only way a browser learns that is by asking again —
 * so the interval is short while something is moving and slow once everything
 * has settled, and it stops entirely on a hidden tab.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, deleteDocument, fetchDocuments, uploadDocument } from "@/lib/api";
import type { LibraryDocument } from "@/lib/types";

const IN_FLIGHT = new Set(["queued", "parsing", "chunking", "embedding"]);

/** Fast while work is moving, slow once it is not. */
const ACTIVE_INTERVAL_MS = 3_000;
const SETTLED_INTERVAL_MS = 25_000;

type Options = {
  signedIn: boolean;
  initial: LibraryDocument[];
  /** Shown when signed out, so the sample library still renders. */
  fallback: LibraryDocument[];
  libraryId?: string | null;
};

export function useLibrary({ signedIn, initial, fallback, libraryId }: Options) {
  const [documents, setDocuments] = useState<LibraryDocument[]>(initial);
  const [uploading, setUploading] = useState<string[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Read inside the interval so the callback is not rebuilt every time a
  // document changes, which would restart the timer on each poll. Synced in an
  // effect rather than during render, so the interval sees the latest documents
  // by the time it ticks without reading a ref mid-render.
  const latest = useRef(documents);
  useEffect(() => {
    latest.current = documents;
  }, [documents]);

  const refresh = useCallback(async () => {
    if (!signedIn) return;
    try {
      setDocuments(await fetchDocuments());
    } catch (cause) {
      // A failed poll is not worth interrupting the user over: the board keeps
      // showing the last known state and the next tick tries again.
      if ((cause as ApiError).code !== "network") setError((cause as Error).message);
    }
  }, [signedIn]);

  useEffect(() => {
    if (!signedIn) return;

    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    async function tick() {
      if (cancelled) return;
      if (document.visibilityState === "visible") await refresh();

      const moving = latest.current.some((entry) => IN_FLIGHT.has(entry.status));
      const delay = moving ? ACTIVE_INTERVAL_MS : SETTLED_INTERVAL_MS;
      if (!cancelled) timer = setTimeout(tick, delay);
    }

    timer = setTimeout(tick, ACTIVE_INTERVAL_MS);

    // A tab that was hidden while work finished has no idea; catch it up as soon
    // as it comes back rather than waiting out the next interval.
    function onVisible() {
      if (document.visibilityState === "visible") refresh();
    }
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [signedIn, refresh]);

  const upload = useCallback(
    async (files: File[]) => {
      if (!signedIn || files.length === 0) return;

      setError(null);
      setUploading(files.map((file) => file.name));

      // Sequential rather than parallel: the library has a document quota, and
      // firing twenty uploads at once turns a quota rejection into twenty
      // simultaneous failures instead of one clear message.
      for (const file of files) {
        try {
          const created = await uploadDocument(file, libraryId ?? undefined);
          // An upsert, not a blind prepend. The poller runs every 3s while
          // anything is in flight, and it can land in the gap between the server
          // committing this document and this response arriving — in which case
          // the list it fetched already contains `created`. Prepending
          // unconditionally then puts one id in the array twice, which React
          // reports as two children sharing a key, and which makes the library
          // column and the pipeline board each render and count the document
          // twice. Filtering first makes the insert idempotent whichever of the
          // two responses lands first.
          setDocuments((current) => [
            created,
            ...current.filter((entry) => entry.id !== created.id),
          ]);
        } catch (cause) {
          const failure = cause as ApiError;
          setError(
            failure.code === "quota_exceeded"
              ? failure.message
              : `${file.name}: ${failure.message}`,
          );
        } finally {
          setUploading((current) => current.filter((name) => name !== file.name));
        }
      }

      await refresh();
    },
    [signedIn, libraryId, refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      if (!signedIn) return;
      const previous = latest.current;
      // Removed optimistically: the row is gone the instant it is confirmed
      // deleted, and a failure restores it rather than leaving the user unsure
      // whether the document survived.
      setDocuments((current) => current.filter((entry) => entry.id !== id));
      setDeletingId(id);

      try {
        await deleteDocument(id);
      } catch (cause) {
        setDocuments(previous);
        setError((cause as ApiError).message);
      } finally {
        setDeletingId(null);
      }
    },
    [signedIn],
  );

  return {
    documents: signedIn ? documents : fallback,
    uploading,
    deletingId,
    error,
    dismissError: () => setError(null),
    upload,
    remove,
    refresh,
  };
}

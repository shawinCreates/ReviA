"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, deleteDocument, fetchDocuments, uploadDocument } from "@/lib/api";
import type { LibraryDocument } from "@/lib/types";

const IN_FLIGHT = new Set(["queued", "parsing", "chunking", "embedding"]);

const ACTIVE_INTERVAL_MS = 3_000;
const SETTLED_INTERVAL_MS = 25_000;

type Options = {
  signedIn: boolean;
  initial: LibraryDocument[];
  fallback: LibraryDocument[];
  libraryId?: string | null;
};

export function useLibrary({ signedIn, initial, fallback, libraryId }: Options) {
  const [documents, setDocuments] = useState<LibraryDocument[]>(initial);
  const [uploading, setUploading] = useState<string[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const latest = useRef(documents);
  useEffect(() => {
    latest.current = documents;
  }, [documents]);

  const refresh = useCallback(async () => {
    if (!signedIn) return;
    try {
      setDocuments(await fetchDocuments());
    } catch (cause) {
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

      for (const file of files) {
        try {
          const created = await uploadDocument(file, libraryId ?? undefined);
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

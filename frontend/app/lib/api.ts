import { apiBaseUrl, getSupabase } from "./supabase";

/**
 * Thin wrapper over fetch that attaches the Supabase access token and unwraps
 * the backend's error envelope so callers see a thrown Error rather than a raw
 * Response.
 *
 * The backend returns `{"error": {"code", "message", "retry_after"?}}` on every
 * failure; see backend/api/errors.py.
 */

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryAfter?: number;

  constructor(
    code: string,
    message: string,
    status: number,
    retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export type Me = {
  id: string;
  email: string;
  created_at: string;
};

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const {
    data: { session },
  } = await getSupabase().auth.getSession();

  if (!session) {
    throw new ApiError("unauthenticated", "Not signed in.", 401);
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access_token}`,
      ...init.headers,
    },
  });

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const error = payload?.error;
    throw new ApiError(
      error?.code ?? "unknown",
      error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      error?.retry_after,
    );
  }

  return payload as T;
}

export function getMe(): Promise<Me> {
  return apiFetch<Me>("/api/me");
}

export type DocumentStatus =
  | "queued"
  | "parsing"
  | "indexing"
  | "ready"
  | "failed";

export type Library = {
  id: string;
  title: string;
  created_at: string;
  document_count: number;
  ready_count: number;
};

export type DocumentSummary = {
  id: string;
  filename: string;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  ingest_cursor: number;
  size_bytes: number;
  mime: string;
  created_at: string;
};

export type LibraryDetail = Library & { documents: DocumentSummary[] };

export type CreatedDocument = {
  id: string;
  status: DocumentStatus;
  filename: string;
  mime: string;
  size_bytes: number;
  upload_url: string;
  storage_path: string;
  expires_in: number;
  /** Must be sent verbatim, or the presigned signature fails. */
  upload_headers: Record<string, string>;
};

export type IngestResult = {
  document_id: string;
  status: DocumentStatus;
  cursor: number;
  pages_written: number;
  chunks_written: number;
  done: boolean;
  error: string | null;
};

export function listLibraries(): Promise<Library[]> {
  return apiFetch<Library[]>("/api/libraries");
}

export function createLibrary(title: string): Promise<Library> {
  return apiFetch<Library>("/api/libraries", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export function getLibrary(id: string): Promise<LibraryDetail> {
  return apiFetch<LibraryDetail>(`/api/libraries/${id}`);
}

export function createDocument(input: {
  library_id: string;
  filename: string;
  mime: string;
  size_bytes: number;
}): Promise<CreatedDocument> {
  return apiFetch<CreatedDocument>("/api/documents", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function ingestDocument(id: string): Promise<IngestResult> {
  return apiFetch<IngestResult>(`/api/documents/${id}/ingest`, {
    method: "POST",
  });
}

export function getDocument(id: string): Promise<DocumentSummary & {
  library_id: string;
  embed_model: string | null;
}> {
  return apiFetch(`/api/documents/${id}`);
}

/**
 * PUT the file straight to Supabase Storage using the presigned URL.
 *
 * Deliberately not `apiFetch`: this request must NOT carry the Authorization
 * header or a JSON content type. The URL's signature includes `Content-Type`,
 * so the exact value returned by the backend has to be sent, and the body is
 * the raw file.
 */
export async function uploadFile(
  created: CreatedDocument,
  file: File,
): Promise<void> {
  const response = await fetch(created.upload_url, {
    method: "PUT",
    headers: created.upload_headers,
    body: file,
  });
  if (!response.ok) {
    throw new ApiError(
      "upload_failed",
      `Upload failed with status ${response.status}.`,
      response.status,
    );
  }
}

import { API_BASE_URL, type Stage } from "@/lib/config";
import type { ChatSession, Citation, LibraryDocument, Message } from "@/lib/types";

export type WireCitation = {
  reference: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number | null;
  ordinal: number;
  snippet: string;
};

export type WireDocument = {
  id: string;
  filename: string;
  extension: string;
  stage: Stage;
  stage_label: string;
  size_bytes: number;
  page_count: number | null;
  error_message: string | null;
  chunk_count?: number | null;
  created_at: string;
  updated_at: string;
};

export type WireSession = {
  id: string;
  library: string;
  title: string;
  message_count?: number | null;
  created_at: string;
  updated_at: string;
};

export type WireMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: WireCitation[];
  created_at: string;
};

type AskResponse = {
  session: WireSession;
  answer: string;
  citations: WireCitation[];
  retrieved: WireCitation[];
  used_context: number;
};

export const REQUEST_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryable = status === 0 || status === 429 || status >= 500;
  }
}

export function clearAccessToken() {
  cachedAccessToken = null;
}

export const UNAUTHENTICATED = "revia:unauthenticated";

function friendly(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiError("That took too long. Check the API is running.", "timeout", 0);
  }
  return new ApiError(
    "Could not reach the API. It may be stopped or unreachable.",
    "network",
    0,
  );
}

async function readError(response: Response): Promise<ApiError> {
  let code = `http_${response.status}`;
  let message = "";

  try {
    const body = await response.json();
    if (body?.error?.code) code = body.error.code;
    if (body?.error?.message) message = body.error.message;
  } catch {
  }

  if (!message) {
    message =
      response.status === 401
        ? "Your session has expired. Sign in again."
        : response.status === 403
          ? "That request was refused."
          : `The API returned ${response.status}.`;
  }

  if (response.status === 401 && typeof window !== "undefined") {
    clearAccessToken();
    window.dispatchEvent(new CustomEvent(UNAUTHENTICATED));
  }

  return new ApiError(message, code, response.status);
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) throw await readError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function browserFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = await accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const signal =
    init.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS);

  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    signal,
    credentials: "include",
    cache: "no-store",
  });
}

let cachedAccessToken: { value: string; at: number } | null = null;

async function accessToken(): Promise<string | null> {
  if (cachedAccessToken && Date.now() - cachedAccessToken.at < 60_000) {
    return cachedAccessToken.value;
  }
  const { createClient } = await import("@/lib/supabase/client");
  const {
    data: { session },
  } = await createClient().auth.getSession();
  const value = session?.access_token ?? null;
  cachedAccessToken = value ? { value, at: Date.now() } : null;
  return value;
}

const MARKER = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

export function toDisplayText(text: string, references?: Set<number>): string {
  return text.replace(MARKER, (match, group: string) => {
    const numbers = group
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);

    if (!references) return match;

    const labels = numbers
      .filter((number) => references.has(Number(number)))
      .map((number) => `S${number}`);
    return labels.length ? `[${labels.join(", ")}]` : match;
  });
}

export function toCitation(wire: WireCitation): Citation {
  return {
    label: `S${wire.reference}`,
    page: wire.page_number ?? 0,
    documentId: wire.document_id,
    filename: wire.filename,
    snippet: wire.snippet,
  };
}

const STAGE_DETAIL: Record<Stage, string> = {
  queued: "Waiting for a worker",
  parsing: "Reading text and page structure",
  chunking: "Slicing pages into chunks",
  embedding: "Writing vectors and the index",
  ready: "Searchable",
  failed: "Stopped",
};

function describe(document: WireDocument): string {
  if (document.stage === "ready") {
    const chunks = document.chunk_count ?? 0;
    const pages = document.page_count;
    if (pages && chunks) return `${pages} pages, ${chunks} chunks`;
    if (chunks) return `${chunks} ${chunks === 1 ? "chunk" : "chunks"}`;
    return STAGE_DETAIL.ready;
  }
  if (document.stage === "failed") {
    return document.error_message ? STAGE_DETAIL.failed : STAGE_DETAIL.failed;
  }
  return STAGE_DETAIL[document.stage];
}

export function toDocument(wire: WireDocument): LibraryDocument {
  return {
    id: wire.id,
    filename: wire.filename,
    sizeBytes: wire.size_bytes,
    pageCount: wire.page_count,
    status: wire.stage,
    stageDetail: describe(wire),
    error: wire.error_message,
    createdAt: wire.created_at,
    owned: true,
  };
}

export function toSession(wire: WireSession): ChatSession {
  return {
    id: wire.id,
    title: wire.title,
    createdAt: wire.created_at,
    messageCount: wire.message_count ?? 0,
  };
}

export function toMessage(wire: WireMessage, retrieved?: number): Message {
  const sources = wire.citations ?? [];
  const references = new Set(sources.map((citation) => citation.reference));
  const citations = sources.map(toCitation);
  const hadContext = retrieved ?? citations.length;

  return {
    id: wire.id,
    role: wire.role,
    content: toDisplayText(wire.content, references),
    citations,
    refused: wire.role === "assistant" && hadContext === 0,
    uncited: wire.role === "assistant" && hadContext > 0 && citations.length === 0,
    createdAt: wire.created_at,
  };
}

export async function pingApi(timeoutMs = 6_000): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) return false;
    const body = (await response.json()) as { status?: string };
    return body.status === "ok";
  } catch {
    return false;
  }
}

export async function fetchDocuments(): Promise<LibraryDocument[]> {
  const body = await parse<{ documents: WireDocument[] }>(
    await browserFetch("/api/v1/documents"),
  );
  return body.documents.map(toDocument);
}

export async function uploadDocument(file: File, libraryId?: string): Promise<LibraryDocument> {
  const form = new FormData();
  form.append("file", file);
  if (libraryId) form.append("library", libraryId);

  const body = await parse<{ document: WireDocument }>(
    await browserFetch("/api/v1/documents/upload", { method: "POST", body: form }),
  );
  return toDocument(body.document);
}

export async function deleteDocument(id: string): Promise<void> {
  await parse<void>(await browserFetch(`/api/v1/documents/${id}`, { method: "DELETE" }));
}

export async function fetchSessions(): Promise<ChatSession[]> {
  const body = await parse<{ sessions: WireSession[] }>(
    await browserFetch("/api/v1/chat/sessions"),
  );
  return body.sessions.map(toSession);
}

export async function fetchSessionMessages(sessionId: string): Promise<Message[]> {
  const body = await parse<{ session: WireSession; messages: WireMessage[] }>(
    await browserFetch(`/api/v1/chat/sessions/${sessionId}`),
  );
  return body.messages.map((message) => toMessage(message));
}

export type AskResult = {
  sessionId: string;
  sessionTitle: string;
  message: Message;
  retrieved: number;
  usedContext: number;
};

export async function askQuestion(
  question: string,
  options: { sessionId?: string | null; libraryId?: string | null } = {},
): Promise<AskResult> {
  try {
    const body = await parse<AskResponse>(
      await browserFetch("/api/v1/chat/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question,
          session: options.sessionId ?? undefined,
          library: options.libraryId ?? undefined,
        }),
      }),
    );

    return {
      sessionId: body.session.id,
      sessionTitle: body.session.title,
      retrieved: body.retrieved.length,
      usedContext: body.used_context,
      message: toMessage(
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: body.answer,
          citations: body.citations,
          created_at: new Date().toISOString(),
        },
        body.retrieved.length,
      ),
    };
  } catch (error) {
    throw friendly(error);
  }
}

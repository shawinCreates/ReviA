export const APP_NAME = "ReviA";

export const APP_TAGLINE = "Answers from your own course material, cited to the page.";

/**
 * Where the Django API lives.
 *
 * The host part is derived from the browser's own hostname rather than
 * hardcoded, because the Supabase auth cookie is scoped to a host and cookies
 * ignore ports. Asking the API on `127.0.0.1:8000` from a page served on
 * `localhost:3000` sends no cookie at all, and every request 401s. Mirroring the
 * page's host keeps the cookie attached without asking anyone to keep two
 * hostname spellings in sync in `.env.local`.
 *
 * Server components forward the cookie explicitly, so they use the loopback
 * address and are unaffected either way.
 */
function defaultApiBaseUrl(): string {
  if (typeof window === "undefined") return "http://127.0.0.1:8000";
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? defaultApiBaseUrl()
);

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

export const SUPPORTED_UPLOAD_EXTENSIONS = [".pdf", ".docx", ".pptx"] as const;

export const STAGES = [
  "queued",
  "parsing",
  "chunking",
  "embedding",
  "ready",
  "failed",
] as const;

export type Stage = (typeof STAGES)[number];

export const STAGE_LABELS: Record<Stage, string> = {
  queued: "Queued",
  parsing: "Parsing",
  chunking: "Chunking",
  embedding: "Embedding",
  ready: "Ready",
  failed: "Failed",
};

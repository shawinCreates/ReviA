export const APP_NAME = "ReviA";

export const APP_TAGLINE = "Answers from your own course material, cited to the page.";

function defaultApiBaseUrl(): string {
  if (typeof window === "undefined") return "http://127.0.0.1:8000";
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? defaultApiBaseUrl()
);

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

// Public site URL used for canonical links and Open Graph metadata. Optional:
// when omitted, relative canonical URLs are used instead.
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "";

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

export const STAGE_BLURBS: Record<Stage, string> = {
  queued: "Accepted and waiting for a worker",
  parsing: "Reading text and page structure",
  chunking: "Slicing pages into retrievable chunks",
  embedding: "Writing vectors and the search index",
  ready: "Searchable, and answering questions",
  failed: "Stopped, with the reason given",
};

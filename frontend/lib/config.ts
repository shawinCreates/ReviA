export const APP_NAME = "EndNote";

export const APP_TAGLINE = "Answers from your own course material, cited to the page.";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

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

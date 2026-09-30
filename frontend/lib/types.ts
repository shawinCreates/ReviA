import type { Stage } from "./config";

export type Role = "user" | "assistant";

export type Citation = {
  label: string;
  page: number;
  documentId: string;
  filename: string;
  snippet: string;
};

export type Source = {
  ordinal: number;
  page: number;
  documentId: string;
  filename: string;
  text: string;
  score: number;
};

export type Message = {
  id: string;
  role: Role;
  content: string;
  citations: Citation[];
  refused: boolean;
  uncited: boolean;
  createdAt: string;
};

export type ChatSession = {
  id: string;
  title: string;
  createdAt: string;
  messageCount: number;
};

export type DocumentStatus = Stage;

export type LibraryDocument = {
  id: string;
  filename: string;
  sizeBytes: number;
  pageCount: number | null;
  status: DocumentStatus;
  stageDetail: string;
  error: string | null;
  createdAt: string;
  owned: boolean;
};

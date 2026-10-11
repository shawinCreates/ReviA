import { cookies } from "next/headers";

import { API_BASE_URL } from "@/lib/config";
import {
  toDocument,
  toMessage,
  toSession,
  type WireDocument,
  type WireMessage,
  type WireSession,
} from "@/lib/api";
import type { ChatSession, LibraryDocument, Message } from "@/lib/types";

const TIMEOUT_MS = 8_000;

async function get<T>(path: string, fallback: T): Promise<T> {
  try {
    const jar = await cookies();
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { cookie: jar.toString() },
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

export type Library = {
  id: string;
  name: string;
  is_default: boolean;
  document_count: number;
  created_at: string;
};

export async function loadLibraries(): Promise<Library[]> {
  const body = await get<{ libraries: Library[] }>("/api/v1/libraries", { libraries: [] });
  return body.libraries;
}

export async function loadDocuments(): Promise<LibraryDocument[]> {
  const body = await get<{ documents: WireDocument[] }>("/api/v1/documents", { documents: [] });
  return body.documents.map(toDocument);
}

export async function loadSessions(): Promise<ChatSession[]> {
  const body = await get<{ sessions: WireSession[] }>("/api/v1/chat/sessions", { sessions: [] });
  return body.sessions.map(toSession);
}

export async function loadSessionMessages(sessionId: string): Promise<Message[]> {
  const body = await get<{ messages: WireMessage[] }>(`/api/v1/chat/sessions/${sessionId}`, {
    messages: [],
  });
  return body.messages.map((message) => toMessage(message));
}

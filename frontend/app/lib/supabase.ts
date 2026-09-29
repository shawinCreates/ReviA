import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Supabase owns auth. The browser holds the session and sends the access token
 * to Django as `Authorization: Bearer`; Django verifies it against Supabase's
 * JWKS and never sees a password. See architecture.md.
 *
 * The anon key is publishable. It is not a secret and is inlined into the
 * client bundle by Next.js, which is exactly what Supabase's own design
 * expects. Row-level security on the tables is what actually protects data.
 */

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set. " +
      "Copy .env.example to .env.local and fill it in.",
  );
}

let client: SupabaseClient | undefined;

export function getSupabase(): SupabaseClient {
  if (!client) {
    client = createClient(url!, anonKey!, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }
  return client;
}

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

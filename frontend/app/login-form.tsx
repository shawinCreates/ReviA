"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { Session } from "@supabase/supabase-js";
import { getMe, ApiError, type Me } from "./lib/api";
import { getSupabase } from "./lib/supabase";
import LibraryView from "./library";

/**
 * Email + password sign-in against Supabase Auth. The session is persisted by
 * the Supabase client; on success the token is forwarded to Django, which
 * verifies it and lazily creates the Profile row that backs the app.
 */
export default function LoginForm() {
  const [session, setSession] = useState<Session | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<{
    userId: string;
    data: Me | null;
    error: string | null;
  } | null>(null);

  // Restore an existing session on load so a refresh does not sign you out.
  useEffect(() => {
    getSupabase().auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = getSupabase().auth.onAuthStateChange(
      (_event, next) => setSession(next),
    );
    return () => sub.subscription.unsubscribe();
  }, []);

  // When a session exists, prove the browser -> Django path works end to end.
  // Results are tagged with the user id so a stale profile from a previous
  // session is never shown for a different user.
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    getMe()
      .then((data) => {
        if (!cancelled) setProfile({ userId: session.user.id, data, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setProfile({
          userId: session.user.id,
          data: null,
          error:
            err instanceof ApiError ? err.message : "Could not reach the API.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  const me = session && profile?.userId === session.user.id ? profile.data : null;
  const meError =
    session && profile?.userId === session.user.id ? profile.error : null;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const supabase = getSupabase();
      const { error: authError } =
        mode === "signin"
          ? await supabase.auth.signInWithPassword({ email, password })
          : await supabase.auth.signUp({ email, password });
      if (authError) setError(authError.message);
    } finally {
      setBusy(false);
    }
  }

  async function onSignOut() {
    await getSupabase().auth.signOut();
  }

  if (session) {
    return (
      <div className="w-full max-w-2xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">EndNote</h1>
            <p className="text-sm text-zinc-500">
              Signed in as{" "}
              <span className="font-mono">{session.user.email}</span>
            </p>
          </div>
          <button
            onClick={onSignOut}
            className="rounded-full border border-solid border-black/[.08] px-4 py-2 text-sm hover:bg-black/[.04] dark:hover:bg-[#1a1a1a]"
          >
            Sign out
          </button>
        </div>
        {meError ? (
          <p className="text-sm text-red-600">{meError}</p>
        ) : me ? (
          <LibraryView email={me.email} />
        ) : (
          <p className="text-sm text-zinc-500">Loading…</p>
        )}
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="w-full max-w-md space-y-4 rounded-lg border border-black/[.08] bg-white p-6 dark:border-white/[.145] dark:bg-black"
    >
      <h2 className="text-lg font-semibold">
        {mode === "signin" ? "Sign in" : "Create an account"}
      </h2>

      <label className="block space-y-1 text-sm">
        <span>Email</span>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded border border-black/[.15] px-3 py-2 dark:border-white/[.2] dark:bg-black"
        />
      </label>

      <label className="block space-y-1 text-sm">
        <span>Password</span>
        <input
          type="password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border border-black/[.15] px-3 py-2 dark:border-white/[.2] dark:bg-black"
        />
      </label>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={busy}
        className="w-full rounded-full bg-foreground px-5 py-2 text-background transition-colors hover:bg-[#383658] disabled:opacity-50"
      >
        {busy ? "Working…" : mode === "signin" ? "Sign in" : "Sign up"}
      </button>

      <button
        type="button"
        onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
        className="w-full text-sm text-zinc-500 hover:underline"
      >
        {mode === "signin"
          ? "Need an account? Sign up"
          : "Already have an account? Sign in"}
      </button>
    </form>
  );
}

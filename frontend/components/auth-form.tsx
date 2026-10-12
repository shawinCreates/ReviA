"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { createClient } from "@/lib/supabase/client";
import { APP_NAME } from "@/lib/config";
import { Alert, ArrowRight, Check } from "@/components/icons";
import { Button } from "@/components/ui";

type Mode = "signin" | "signup";

const COPY = {
  signin: {
    title: "Sign in",
    lead: "Pick up a conversation you left open.",
    submit: "Sign in",
    switchText: "No account yet?",
    switchLabel: "Create one",
  },
  signup: {
    title: "Create an account",
    lead: "Your library is private to you and stays that way.",
    submit: "Create account",
    switchText: "Already registered?",
    switchLabel: "Sign in",
  },
} as const;

export function AuthForm({
  mode: initialMode = "signin",
  next = "/chat",
  onSuccess,
  compact = false,
}: {
  mode?: Mode;
  next?: string;
  onSuccess?: () => void;
  compact?: boolean;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const copy = COPY[mode];

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);

    const supabase = createClient();
    const result =
      mode === "signin"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({
            email,
            password,
            options: {
              emailRedirectTo: new URL("/auth/callback", window.location.origin).toString(),
            },
          });

    if (result.error) {
      setError(result.error.message);
      setBusy(false);
      return;
    }

    if (mode === "signup" && !result.data.session) {
      setNotice("Check your inbox to confirm the address, then sign in.");
      setBusy(false);
      return;
    }

    onSuccess?.();
    router.push(next);
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className={compact ? "" : "w-full"}>
      <div className={compact ? "" : "mb-8"}>
        <h2 className={compact ? "text-[26px] font-medium tracking-[-0.025em]" : "text-title"}>
          {copy.title}
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-muted">{copy.lead}</p>
      </div>

      <div className="space-y-4">
        <label className="block">
          <span className="text-[12px] text-ink-soft">Email</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1.5 h-10 w-full rounded-none border border-line bg-surface px-3 text-[14px] text-ink transition-colors placeholder:text-faint focus:border-accent"
            placeholder="you@college.ac.uk"
          />
        </label>

        <label className="block">
          <span className="text-[12px] text-ink-soft">Password</span>
          <input
            type="password"
            required
            minLength={8}
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1.5 h-10 w-full rounded-none border border-line bg-surface px-3 text-[14px] text-ink transition-colors placeholder:text-faint focus:border-accent"
            placeholder="At least 8 characters"
          />
        </label>
      </div>

      {error ? (
        <p
          role="alert"
          className="mt-4 flex items-start gap-2 border-l-2 border-danger bg-danger/10 px-3 py-2.5 text-[12px] leading-relaxed text-danger"
        >
          <Alert size={14} className="mt-px shrink-0" />
          {error}
        </p>
      ) : null}

      {notice ? (
        <p
          role="status"
          className="mt-4 flex items-start gap-2 border-l-2 border-success bg-success/10 px-3 py-2.5 text-[12px] leading-relaxed text-success"
        >
          <Check size={14} className="mt-px shrink-0" />
          {notice}
        </p>
      ) : null}

      <Button type="submit" size="lg" className="mt-6 w-full" disabled={busy}>
        {busy ? "Working" : copy.submit}
        {!busy ? <ArrowRight /> : null}
      </Button>

      <p className="mt-5 text-center text-[12px] text-muted">
        {copy.switchText}{" "}
        <button
          type="button"
          onClick={() => {
            setMode(mode === "signin" ? "signup" : "signin");
            setError(null);
            setNotice(null);
          }}
          className="text-ink underline underline-offset-4"
        >
          {copy.switchLabel}
        </button>
      </p>

      <p className="mt-6 border-t border-line pt-5 text-center text-[11px] leading-relaxed text-faint">
        {APP_NAME} keeps the email above and the documents you upload. Nothing else
        about you is stored.
      </p>
    </form>
  );
}

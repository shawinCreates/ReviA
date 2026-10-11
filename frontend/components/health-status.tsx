"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ReviaMark } from "@/components/icons";
import { APP_NAME } from "@/lib/config";
import { pingApi } from "@/lib/api";

const POLL_MS = 4_000;

export function WakeServer() {
  useEffect(() => {
    void pingApi();
  }, []);
  return null;
}

export function HealthGate({ path }: { path: string }) {
  const router = useRouter();
  const [slow, setSlow] = useState(false);

  const poll = useCallback(async () => {
    if (await pingApi()) {
      router.refresh();
      return true;
    }
    return false;
  }, [router]);

  useEffect(() => {
    let cancelled = false;
    const started = Date.now();

    async function tick() {
      if (cancelled) return;
      if (await poll()) return;
      if (!cancelled && Date.now() - started > 20_000) setSlow(true);
      if (!cancelled) setTimeout(tick, POLL_MS);
    }

    void tick();
    return () => {
      cancelled = true;
    };
  }, [poll]);

  return (
    <div className="relative flex h-dvh flex-col items-center justify-center bg-paper px-6 text-center hairline-grid">
      <div className="warm-wash absolute inset-0 -z-10" />
      <ReviaMark size={28} className="text-ink" />
      <h1 className="mt-6 font-[family-name:var(--font-display)] text-[1.5rem] tracking-[-0.01em] text-ink">
        Waking the server
      </h1>
      <p className="mt-3 max-w-[38ch] text-[14px] leading-relaxed text-muted">
        {APP_NAME} sleeps when it is idle. Starting it back up takes about a
        minute.
      </p>
      <div className="mt-8 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.16em] text-faint">
        <span className="size-1.5 animate-pulse rounded-full bg-warning" />
        <span>{slow ? "Still starting — hang tight" : path}</span>
      </div>
    </div>
  );
}

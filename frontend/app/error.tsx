"use client";

import Link from "next/link";

export default function Error({ reset }: { reset: () => void }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-paper px-6 text-center">
      <h1 className="font-[family-name:var(--font-display)] text-[1.5rem] tracking-[-0.01em] text-ink">
        Something went wrong
      </h1>
      <p className="mt-3 max-w-[38ch] text-[14px] leading-relaxed text-muted">
        We could not load this page. Refreshing usually fixes it, or you can start
        over from the home page.
      </p>
      <div className="mt-8 flex flex-col sm:flex-row items-center gap-3">
        <button
          type="button"
          onClick={() => reset()}
          className="inline-flex items-center justify-center gap-2 rounded-none border border-line bg-surface px-4 py-2 text-[13px] text-ink hover:bg-sunk"
        >
          Try again
        </button>
        <Link
          href="/"
          className="inline-flex items-center justify-center gap-2 rounded-none border border-line bg-surface px-4 py-2 text-[13px] text-muted hover:bg-sunk"
        >
          Home page
        </Link>
      </div>
    </div>
  );
}

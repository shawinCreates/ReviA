import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-paper px-6 text-center">
      <h1 className="font-[family-name:var(--font-display)] text-[1.5rem] tracking-[-0.01em] text-ink">
        Not found
      </h1>
      <p className="mt-3 max-w-[38ch] text-[14px] leading-relaxed text-muted">
        There is nothing at this address.
      </p>
      <div className="mt-8">
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

import Link from "next/link";
import type { ReactNode } from "react";

import { APP_NAME } from "@/lib/config";
import { ButtonLink } from "@/components/ui";

export function Wordmark({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="group inline-flex items-baseline gap-1.5">
      <span className="text-[19px] font-medium tracking-[-0.02em] text-ink">{APP_NAME}</span>
      <span className="h-1 w-1 translate-y-[-3px] rounded-full bg-ink transition-transform duration-200 group-hover:scale-150" />
    </Link>
  );
}

export function SiteHeader({ children }: { children?: ReactNode }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-8 px-6">
        <Wordmark />
        <nav className="hidden items-center gap-7 text-[13px] text-muted md:flex">
          <Link href="/#how" className="transition-colors hover:text-ink">
            How it works
          </Link>
          <Link href="/#features" className="transition-colors hover:text-ink">
            Features
          </Link>
          <Link href="/#pricing" className="transition-colors hover:text-ink">
            Pricing
          </Link>
          <Link href="/pipeline" className="transition-colors hover:text-ink">
            Pipeline
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {children ?? (
            <>
              <ButtonLink href="/login" variant="ghost" size="sm">
                Sign in
              </ButtonLink>
              <ButtonLink href="/chat" size="sm">
                Try {APP_NAME}
              </ButtonLink>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto max-w-6xl px-6 py-14">
        <div className="grid gap-10 sm:grid-cols-3">
          <div>
            <Wordmark />
            <p className="mt-3 max-w-[28ch] text-[13px] leading-relaxed text-muted">
              Answers drawn from your own uploaded material, with the page cited
              for every claim.
            </p>
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-faint">Product</p>
            <ul className="mt-4 space-y-2.5 text-[13px] text-muted">
              <li>
                <Link href="/chat" className="transition-colors hover:text-ink">
                  Chat
                </Link>
              </li>
              <li>
                <Link href="/pipeline" className="transition-colors hover:text-ink">
                  Ingestion pipeline
                </Link>
              </li>
              <li>
                <Link href="/#pricing" className="transition-colors hover:text-ink">
                  Pricing
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-faint">Account</p>
            <ul className="mt-4 space-y-2.5 text-[13px] text-muted">
              <li>
                <Link href="/login" className="transition-colors hover:text-ink">
                  Sign in
                </Link>
              </li>
              <li>
                <Link href="/login?mode=signup" className="transition-colors hover:text-ink">
                  Create an account
                </Link>
              </li>
            </ul>
          </div>
        </div>
        <p className="mt-12 border-t border-line pt-6 text-[12px] text-faint">
          Unrelated to EndNote from Clarivate. A student-built tool, not affiliated.
        </p>
      </div>
    </footer>
  );
}

import Link from "next/link";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";
import { Wordmark } from "@/components/chrome";

export const metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string; next?: string }>;
}) {
  const params = await searchParams;
  const mode = params.mode === "signup" ? "signup" : "signin";
  const next = params.next ?? "/chat";

  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <div className="relative hidden overflow-hidden border-r border-line bg-surface lg:block">
        <div className="warm-wash absolute inset-0" />
        <div className="hairline-grid absolute inset-0 opacity-50" />
        <div className="relative flex h-full flex-col justify-between p-10 xl:p-12">
          <Wordmark />
          <div className="max-w-[40ch]">
            <h1 className="font-[family-name:var(--font-display)] text-[1.75rem] leading-[1.06] tracking-[-0.02em] xl:text-[2.25rem]">
              Your notes, answered from your notes.
            </h1>
            <p className="mt-6 text-[15px] leading-relaxed text-ink-soft">
              Every answer is assembled from the pages you uploaded, and every claim
              carries the page it came from. If the material does not cover it, you
              get told that instead of an answer.
            </p>
          </div>
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">
            20 documents per library &middot; 25MB per file &middot; PDF, DOCX, PPTX
          </p>
        </div>
      </div>

      <div className="flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-[380px]">
          <div className="mb-10 lg:hidden">
            <Wordmark />
          </div>
          <Suspense fallback={null}>
            <AuthForm mode={mode} next={next} />
          </Suspense>
          <p className="mt-8 flex justify-center">
            <Link
              href="/"
              className="inline-flex items-center border border-line px-3.5 py-2 text-[13px] text-muted transition-colors duration-200 hover:border-ink hover:text-ink motion-reduce:transition-none"
            >
              Back to the home page
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

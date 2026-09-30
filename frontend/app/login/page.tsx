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
        <div className="relative flex h-full flex-col justify-between p-12">
          <Wordmark />
          <div className="max-w-[40ch]">
            <p className="text-[34px] font-medium leading-[1.1] tracking-[-0.03em] text-ink">
              Your notes, answered from your notes.
            </p>
            <p className="mt-6 text-[15px] leading-relaxed text-muted">
              Every answer is assembled from the pages you uploaded, and every claim
              carries the page it came from. If the material does not cover it, you
              get told that instead of an answer.
            </p>
          </div>
          <p className="font-mono text-[11px] text-faint">
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
          <p className="mt-8 text-center text-[12px] text-muted">
            <Link href="/" className="text-muted underline underline-offset-4 hover:text-ink">
              Back to the home page
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

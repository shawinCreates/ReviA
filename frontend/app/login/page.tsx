import Link from "next/link";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";
import { Wordmark } from "@/components/chrome";

export const metadata = {
  title: "Sign in",
  description:
    "Sign in to ReviA to access your private library, upload documents, and keep your conversations between visits.",
  robots: { index: false, follow: true },
  alternates: { canonical: "/login" },
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string; next?: string }>;
}) {
  const params = await searchParams;
  const mode = params.mode === "signup" ? "signup" : "signin";
  const next = params.next ?? "/chat";

  return (
    <div className="flex min-h-dvh items-center justify-center px-6 py-16">
      <div className="w-full max-w-[380px]">
        <h1 className="sr-only">{mode === "signup" ? "Create an account" : "Sign in"}</h1>
        <div className="mb-10">
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
  );
}

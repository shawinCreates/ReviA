"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { createClient } from "@/lib/supabase/client";
import { Wordmark } from "@/components/chrome";
import { Button, ButtonLink } from "@/components/ui";

export function AppHeader({ nav }: { nav?: ReactNode }) {
  return (
    <header className="shrink-0 border-b border-line bg-paper">
      <div className="flex h-14 items-center gap-6 px-5">
        <Wordmark />
        <nav className="hidden items-center gap-6 text-[13px] text-muted md:flex">
          <Link href="/chat" className="transition-colors hover:text-ink">
            Chat
          </Link>
          <Link href="/pipeline" className="transition-colors hover:text-ink">
            Pipeline
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-2.5">
          {nav ?? <AccountSlot />}
        </div>
      </div>
    </header>
  );
}

function AccountSlot() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    createClient()
      .auth.getUser()
      .then(({ data }) => {
        if (active) setEmail(data.user?.email ?? null);
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  if (!ready) {
    return <div className="h-8 w-24" />;
  }

  if (!email) {
    return (
      <>
        <ButtonLink href="/login" variant="ghost" size="sm">
          Sign in
        </ButtonLink>
        <ButtonLink href="/login?mode=signup" size="sm">
          Create account
        </ButtonLink>
      </>
    );
  }

  return (
    <>
      <span className="hidden text-[13px] text-muted sm:inline">{email}</span>
      <Button
        variant="quiet"
        size="sm"
        onClick={async () => {
          await createClient().auth.signOut();
          router.push("/");
          router.refresh();
        }}
      >
        Sign out
      </Button>
    </>
  );
}

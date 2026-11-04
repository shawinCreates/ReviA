"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";

import { createClient } from "@/lib/supabase/client";
import { clearAccessToken, UNAUTHENTICATED } from "@/lib/api";

const AUTH_ROUTES = ["/login", "/auth/callback"];

function isAuthRoute(pathname: string) {
  return AUTH_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
}

export function AuthWatcher() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const signOut = () => {
      clearAccessToken();
      if (!isAuthRoute(pathname)) {
        router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      }
    };

    const supabase = createClient();

    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_OUT") {
        signOut();
      }
    });

    const onUnauthenticated = () => signOut();
    window.addEventListener(UNAUTHENTICATED, onUnauthenticated);

    return () => {
      window.removeEventListener(UNAUTHENTICATED, onUnauthenticated);
      data.subscription.unsubscribe();
    };
  }, [pathname, router]);

  return null;
}

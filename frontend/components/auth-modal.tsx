"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AuthForm } from "@/components/auth-form";
import { Close } from "@/components/icons";
import { ButtonLink } from "@/components/ui";

export const UPLOAD_REASON =
  "Create a free account to upload documents. Your files stay private to you, and nothing is kept once you delete them.";

export function AuthModal({
  open,
  onClose,
  next,
  reason = UPLOAD_REASON,
}: {
  open: boolean;
  onClose: () => void;
  next: string;
  reason?: string;
}) {
  const router = useRouter();

  useEffect(() => {
    if (!open) return;

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 bg-ink/25 backdrop-blur-[2px]"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Sign in to continue"
        className="relative w-full max-w-[420px] rounded-none border border-line bg-surface p-7 shadow-lift sm:p-8"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute top-5 right-5 text-faint transition-colors hover:text-ink motion-reduce:transition-none"
        >
          <Close size={16} />
        </button>

        <p className="max-w-[34ch] text-[13px] leading-relaxed text-ink-soft">{reason}</p>

        <div className="mt-7">
          <AuthForm
            compact
            next={next}
            onSuccess={() => {
              onClose();
              router.refresh();
            }}
          />
        </div>

        <div className="mt-6 border-t border-line pt-5">
          <ButtonLink href="/chat" variant="ghost" size="sm" className="w-full" onClick={onClose}>
            Keep looking around instead
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}

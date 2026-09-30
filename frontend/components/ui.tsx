import Link from "next/link";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

const CONTROL =
  "inline-flex items-center justify-center gap-2 rounded-[5px] text-sm font-medium transition-all duration-200 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45";

const SIZES = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4",
  lg: "h-12 px-6 text-[15px]",
};

const VARIANTS = {
  solid: "bg-ink text-white hover:bg-ink-soft",
  outline: "border border-line bg-surface text-ink hover:border-line-strong hover:bg-sunk",
  ghost: "text-muted hover:bg-sunk hover:text-ink",
  quiet: "bg-sunk text-ink hover:bg-line",
};

type ButtonProps = {
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
} & ComponentPropsWithoutRef<"button">;

export function Button({
  variant = "solid",
  size = "md",
  className = "",
  ...props
}: ButtonProps) {
  return <button className={`${CONTROL} ${SIZES[size]} ${VARIANTS[variant]} ${className}`} {...props} />;
}

type ButtonLinkProps = {
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
} & ComponentPropsWithoutRef<typeof Link>;

export function ButtonLink({
  variant = "solid",
  size = "md",
  className = "",
  ...props
}: ButtonLinkProps) {
  return <Link className={`${CONTROL} ${SIZES[size]} ${VARIANTS[variant]} ${className}`} {...props} />;
}

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "blue" | "green" | "yellow" | "red";
  children: ReactNode;
}) {
  const tones = {
    neutral: "bg-sunk text-muted",
    blue: "bg-pale-blue-bg text-pale-blue-ink",
    green: "bg-pale-green-bg text-pale-green-ink",
    yellow: "bg-pale-yellow-bg text-pale-yellow-ink",
    red: "bg-pale-red-bg text-pale-red-ink",
  } as const;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.06em] ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={`rounded-[10px] border border-line bg-surface transition-shadow duration-200 hover:shadow-whisper ${className}`}
    >
      {children}
    </div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-faint">{children}</p>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded-[4px] border border-line bg-sunk px-1.5 py-0.5 font-mono text-[11px] text-muted">
      {children}
    </kbd>
  );
}

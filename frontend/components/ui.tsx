import Link from "next/link";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

const CONTROL =
  "inline-flex items-center justify-center gap-2 rounded-none text-sm font-medium transition-all duration-200 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45";

const SIZES = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4",
  lg: "h-12 px-6 text-[15px]",
};

const VARIANTS = {
  solid: "bg-accent text-white hover:bg-ink/85",
  outline: "border border-line-strong bg-surface text-ink hover:border-ink",
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
  tone?: "neutral" | "accent" | "success" | "warning" | "danger";
  children: ReactNode;
}) {
  const tones = {
    neutral: "bg-sunk text-muted",
    accent: "bg-accent-soft text-accent",
    success: "bg-success/10 text-success",
    warning: "bg-warning/10 text-warning",
    danger: "bg-danger/10 text-danger",
  } as const;

  return (
    <span
      className={`inline-flex items-center rounded-none px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em] ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <div className={`rounded-none border border-line bg-surface ${className}`}>{children}</div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-faint">{children}</p>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded-none border border-line bg-sunk px-1.5 py-0.5 font-mono text-[11px] text-muted">
      {children}
    </kbd>
  );
}

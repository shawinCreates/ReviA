"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

export function Reveal({
  children,
  index = 0,
  as: Tag = "div",
  className = "",
}: {
  children: ReactNode;
  index?: number;
  as?: "div" | "section" | "li" | "article";
  className?: string;
}) {
  const ref = useRef<HTMLElement | null>(null);

  const [shown, setShown] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || shown) return;

    if (typeof IntersectionObserver === "undefined") {
      const timer = setTimeout(() => setShown(true), 0);
      return () => clearTimeout(timer);
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setShown(true);
            observer.disconnect();
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.1 },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [shown]);

  return (
    <Tag
      ref={ref as never}
      style={{ "--reveal-index": index } as React.CSSProperties}
      className={`reveal ${shown ? "reveal-in" : ""} ${className}`}
    >
      {children}
    </Tag>
  );
}

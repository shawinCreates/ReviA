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

  // Starts false on both sides, deliberately. The first version read a browser
  // API to decide this: `typeof IntersectionObserver === "undefined"`, which is
  // true on the server and false in a browser, so the server rendered
  // `reveal reveal-in` and the client's first render expected `reveal`. React
  // reported a hydration mismatch on every load and refused to patch the class,
  // which left above-the-fold content visible on arrival and then hidden for
  // the frame before the observer revealed it again.
  //
  // The no-observer case is handled in the effect instead, where a value that
  // can only be known in the browser belongs. `app/layout.tsx` restores the
  // content for JS-disabled visitors with a `<noscript>` override, since the
  // server now ships this hidden.
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || shown) return;

    if (typeof IntersectionObserver === "undefined") {
      // Nothing will ever intersect, so this element would sit at opacity 0
      // forever and take the page's content with it. Reveal on the next tick
      // rather than synchronously: `react-hooks/set-state-in-effect` is right
      // that a bare setState here is the shape of the derived-state antipattern,
      // and deferring it keeps this an external-system notification (the DOM
      // cannot tell us anything) instead of a value derived from props.
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

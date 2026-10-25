"use client";

import { useEffect, useRef, useState } from "react";

const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%+=";
const DURATION_MS = 700;

type Props = {
  text: string;
  as?: "h1" | "h2" | "h3" | "p";
  className?: string;
};

/**
 * A pixel-face heading that resolves from scrambled glyphs the first time it scrolls into view.
 * The final text sets the layout and is what screen readers get, so nothing shifts and nothing is read twice.
 * With reduced motion, or before scripts run, the final text shows as is.
 */
export function PixelHeading({ text, as = "h2", className = "" }: Props) {
  const ref = useRef<HTMLHeadingElement>(null);
  const Tag = as;
  const [shown, setShown] = useState<string | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        observer.disconnect();
        const start = performance.now();
        const tick = (now: number) => {
          const progress = Math.min(1, (now - start) / DURATION_MS);
          const settled = Math.floor(progress * text.length);
          setShown(
            progress >= 1
              ? null
              : [...text]
                  .map((ch, i) =>
                    i < settled || ch === " " || !/[A-Za-z0-9]/.test(ch)
                      ? ch
                      : (GLYPHS[Math.floor(Math.random() * GLYPHS.length)] ?? ch),
                  )
                  .join(""),
          );
          if (progress < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [text]);

  return (
    <Tag ref={ref} className={`pixel relative ${className}`}>
      <span className={shown === null ? undefined : "invisible"}>{text}</span>
      {shown === null ? null : (
        <span aria-hidden className="absolute inset-0">
          {shown}
        </span>
      )}
    </Tag>
  );
}

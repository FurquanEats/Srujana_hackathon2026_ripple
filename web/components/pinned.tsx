"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The device stays centred while its headline changes, as the visitor scrolls through `captions.length` screens.
 * Before scripts run, and with reduced motion, the first caption shows and the section scrolls normally.
 */
export function Pinned({
  captions,
  children,
}: {
  captions: readonly { title: string; body: string }[];
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => {
      const { top, height } = el.getBoundingClientRect();
      const progress = Math.min(Math.max(-top / Math.max(height - window.innerHeight, 1), 0), 0.999);
      setIndex(Math.floor(progress * captions.length));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [captions.length]);

  const caption = captions[index] ?? captions[0];
  return (
    <div ref={ref} style={{ height: `${captions.length * 90}svh` }} className="relative">
      <div className="sticky top-0 flex h-svh flex-col items-center justify-start gap-6 overflow-hidden px-5 pt-20 pb-6 md:gap-8 md:pt-24">
        <div className="min-h-[7.5rem] shrink-0 text-center" aria-live="polite">
          <h2 className="pixel text-[24px] md:text-[30px]">{caption?.title}</h2>
          <p className="mx-auto mt-4 max-w-[50ch] text-[14px] leading-relaxed text-muted">{caption?.body}</p>
        </div>
        {/* The device is sized to the window's height as well as its width, so the headline never slides under the
            section's top edge on a short window. */}
        <div className="w-full max-w-[min(64rem,calc((100svh-19rem)*1.55))]">{children}</div>
        <ol aria-hidden className="flex gap-2">
          {captions.map((c, i) => (
            <li key={c.title} className={`h-1.5 w-6 ${i === index ? "bg-accent" : "bg-grey-700"}`} />
          ))}
        </ol>
      </div>
    </div>
  );
}

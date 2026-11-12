"use client";

import type { ReactNode } from "react";

type MarqueeProps = {
  items: string[];
  reverse?: boolean;
  className?: string;
};

export function Marquee({ items, reverse = false, className }: MarqueeProps) {
  const row = [...items, ...items];
  return (
    <div className={`group relative flex overflow-hidden ${className ?? ""}`} aria-hidden>
      <div
        className="flex shrink-0 animate-marquee items-center gap-10 pr-10 group-hover:[animation-play-state:paused]"
        style={reverse ? { animationDirection: "reverse" } : undefined}
      >
        {row.map((item, index) => (
          <span key={`${item}-${index}`} className="flex items-center gap-10 whitespace-nowrap font-mono text-[11px] uppercase tracking-[0.3em] text-muted">
            {item}
            <span className="h-1.5 w-1.5 rotate-45 bg-accent" />
          </span>
        ))}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";

import { secondsLeft } from "@/lib/conversation/cooldown";

/** Whole seconds left until `until` (ms since epoch), re-rendering as it ticks; 0 when done. */
export function useCountdown(until: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until === null) return;
    const tick = () => setNow(Date.now());
    const first = window.setTimeout(tick, 0);
    const interval = window.setInterval(tick, 250);
    // One last tick right after the deadline, then stop ticking.
    const end = window.setTimeout(() => {
      window.clearInterval(interval);
      tick();
    }, Math.max(0, until - Date.now()) + 50);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(interval);
      window.clearTimeout(end);
    };
  }, [until]);
  return until === null ? 0 : secondsLeft(until, now);
}

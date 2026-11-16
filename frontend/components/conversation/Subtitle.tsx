"use client";

import { useEffect, useState } from "react";

import { isolateLatin } from "@/lib/text/bidi";

const CHARS_PER_TICK = 2;
const TICK_MS = 20;

type Props = {
  text: string;
  lang: string;
  dir: "ltr" | "rtl";
  /** Called once the text is fully shown (the avatar stops "speaking"). */
  onDone: () => void;
};

/**
 * The avatar's subtitle: types in once (instantly with reduced motion). Screen readers get
 * the full text once through the polite live region, not character by character.
 */
export function Subtitle({ text, lang, dir, onDone }: Props) {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let count = 0;
    const id = setInterval(() => {
      count = reduced ? text.length : Math.min(text.length, count + CHARS_PER_TICK);
      setShown(count);
      if (count >= text.length) {
        clearInterval(id);
        onDone();
      }
    }, TICK_MS);
    return () => clearInterval(id);
  }, [text, onDone]);

  return (
    <p
      aria-live="polite"
      lang={lang}
      dir={dir}
      className="mx-auto max-w-2xl text-center text-sm leading-relaxed text-mist-200 sm:text-base"
    >
      <span className="sr-only">{text}</span>
      {/* The invisible copy reserves the final height so the layout does not jump while typing. */}
      <span aria-hidden="true" className="grid">
        <span className="invisible col-start-1 row-start-1">{dir === "rtl" ? isolateLatin(text) : text}</span>
        <span className="col-start-1 row-start-1">
          {dir === "rtl" ? isolateLatin(text.slice(0, shown)) : text.slice(0, shown)}
        </span>
      </span>
    </p>
  );
}

"use client";

import { useEffect, useRef } from "react";

import type { AnswerMessage } from "@/hooks/useConversation";
import type { Dictionary } from "@/lib/i18n/config";
import { isolateLatin } from "@/lib/text/bidi";
import { spaceArabicLatin } from "@/lib/text/spacing";

import { SourceChips } from "./SourceChips";

type Props = { answer: AnswerMessage; errorText: string | null; t: Dictionary; fallbackLang: string };

/**
 * A live answer under the avatar. Tokens render as they stream (not announced one by one);
 * the polite live region announces the final answer once. Long answers scroll inside this box
 * so the page itself never scrolls.
 */
export function AnswerSubtitle({ answer, errorText, t, fallbackLang }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const finished = answer.status !== "streaming";
  const lang = answer.language ?? fallbackLang;
  const text = spaceArabicLatin(answer.text);

  useEffect(() => {
    const box = scroller.current;
    if (box) box.scrollTop = box.scrollHeight; // follow the newest text
  }, [answer.text, errorText]);

  const announcement = [
    text,
    answer.status === "stopped" ? `(${t.conversation.stopped})` : "",
    errorText ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div
        ref={scroller}
        role="region"
        aria-label={t.conversation.answerLabel}
        tabIndex={0}
        className="max-h-[9.5rem] overflow-y-auto rounded-md text-center text-sm leading-relaxed text-mist-200 sm:max-h-[11rem] sm:text-base"
      >
        {answer.text && (
          <p lang={lang} dir={lang === "ar" ? "rtl" : "ltr"} className="whitespace-pre-line">
            {lang === "ar" ? isolateLatin(text) : text}
            {!finished && <span aria-hidden="true" className="ms-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-accent motion-reduce:animate-none" />}
          </p>
        )}
        {!answer.text && !finished && (
          <p className="text-mist-400">
            <span className="sr-only">{t.conversation.thinking}</span>
            <span aria-hidden="true" className="inline-flex gap-1">
              {[0, 150, 300].map((delay) => (
                <span
                  key={delay}
                  className="size-1.5 animate-pulse rounded-full bg-mist-400 motion-reduce:animate-none"
                  style={{ animationDelay: `${delay}ms` }}
                />
              ))}
            </span>
          </p>
        )}
        {answer.status === "stopped" && (
          <p className="mt-1 text-xs text-mist-400">— {t.conversation.stopped}</p>
        )}
        {errorText && <p className="mt-1 text-sm text-accent">{errorText}</p>}
        {finished && <SourceChips sources={answer.sources} label={t.conversation.sources} />}
      </div>
      <p aria-live="polite" className="sr-only">
        {finished ? announcement : ""}
      </p>
    </div>
  );
}

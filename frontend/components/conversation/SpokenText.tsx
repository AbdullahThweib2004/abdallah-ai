"use client";

import { type ReactNode, useMemo } from "react";

import { spaceArabicLatin } from "@/lib/text/spacing";
import { type Token, tokenize } from "@/lib/voice/timing";
import { type EntryView, wordState } from "@/lib/voice/transcript";

type Props = {
  /** The entry's text as received (offsets of the voice timing refer to it). */
  text: string;
  lang: string;
  rtl: boolean;
  view: EntryView;
  /** Matches the voice owner ("greeting", "answer:<id>"): the live loop finds the words by it. */
  entryKey: string;
};

// Arabic LETTERS only: Arabic punctuation (\u060C \u061B \u061F) may follow an English word.
const ARABIC_LETTER = /[\u0621-\u064A\u0671-\u06D3]/;
const LATIN = /[A-Za-z0-9]/;
const isLatin = (token: Token) => LATIN.test(token.text) && !ARABIC_LETTER.test(token.text);
// Sentence punctuation after an English word stays outside its <bdi>, in the right-to-left
// flow (as lib/text/bidi.tsx does): "C++." renders as <bdi>C++</bdi>. in Arabic text.
const TRAILING = /[.,:;!?\u060C\u061B\u061F\u2026]+$/;

/**
 * One transcript entry as word spans (`.tw`, data-s/data-e = offsets in `text`, data-state =
 * spoken | current | pending). The spans are presentation only (aria-hidden); screen readers
 * read the plain copy. In right-to-left text, consecutive English words share one <bdi> so
 * "AI Developer Assistant" keeps its word order and still highlights word by word.
 */
export function SpokenText({ text, lang, rtl, view, entryKey }: Props) {
  const tokens = useMemo(() => tokenize(text), [text]);

  const nodes: ReactNode[] = [];
  let latinRun: ReactNode[] | null = null;
  let previousEnd = 0;
  const flushRun = (key: number) => {
    if (latinRun?.length) {
      nodes.push(
        <bdi key={`b${key}`} dir="ltr">
          {latinRun}
        </bdi>,
      );
    }
    latinRun = null;
  };

  tokens.forEach((token, index) => {
    const gap = text.slice(previousEnd, token.start);
    const state = wordState(view, token.start, token.end);
    const span = (content: string, key: string) => (
      <span key={key} className="tw" data-s={token.start} data-e={token.end} data-state={state}>
        {content}
      </span>
    );
    if (rtl && isLatin(token)) {
      // The word's punctuation tail is a second span with the same timing, outside the <bdi>.
      const tail = token.text.match(TRAILING)?.[0] ?? "";
      const core = span(token.text.slice(0, token.text.length - tail.length), `${token.start}`);
      if (latinRun && !gap.includes("\n")) {
        latinRun.push(gap, core);
      } else {
        flushRun(index);
        nodes.push(gap);
        latinRun = [core];
      }
      if (tail) {
        flushRun(index);
        nodes.push(span(tail, `${token.start}t`));
      }
    } else {
      flushRun(index);
      nodes.push(gap, span(spaceArabicLatin(token.text), `${token.start}`));
    }
    previousEnd = token.end;
  });
  flushRun(tokens.length);

  return (
    <p
      lang={lang}
      dir={rtl ? "rtl" : "ltr"}
      data-entry={entryKey}
      data-mode={view.mode}
      className="transcript-text whitespace-pre-line text-[0.95rem] leading-[1.75]"
    >
      <span className="sr-only">{spaceArabicLatin(text)}</span>
      <span aria-hidden="true">{nodes}</span>
    </p>
  );
}

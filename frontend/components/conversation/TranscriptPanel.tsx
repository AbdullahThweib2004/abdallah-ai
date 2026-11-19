"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { AnswerMessage } from "@/hooks/useConversation";
import type { Dictionary } from "@/lib/i18n/config";
import { type EntryView, type LiveProgress, entryView, wordState } from "@/lib/voice/transcript";
import type { VoiceRecord } from "@/lib/voice/transcript";

import { SourceChips } from "./SourceChips";
import { SpokenText } from "./SpokenText";

export type TranscriptEntry =
  | { kind: "greeting"; key: "greeting"; text: string; lang: string; rtl: boolean; record: VoiceRecord | undefined }
  | {
      kind: "answer";
      key: string;
      question: string;
      answer: AnswerMessage;
      lang: string;
      rtl: boolean;
      record: VoiceRecord | undefined;
      errorText: string | null;
    };

type Progress = (LiveProgress & { owner: string }) | null;

type Props = {
  t: Dictionary;
  entries: TranscriptEntry[];
  /** Word timing of what is being voiced now (read every animation frame). */
  progress: () => Progress;
  /** panel: desktop side card; compact: the latest entry under the robot (mobile); sheet: all
   * entries in a bottom sheet (mobile). */
  variant: "panel" | "compact" | "sheet";
  onOpenSheet?: () => void;
  onClose?: () => void;
};

const MARGIN = 28;

/**
 * Everything Abdallah AI says: the greeting, then each answer under the visitor's question.
 * Words light up in sync with the voice (see lib/voice/transcript.ts); the live entry is
 * updated directly in the DOM every frame (no React render per frame). Follows the current
 * word unless the visitor scrolls up ("Jump to now" brings it back).
 */
export function TranscriptPanel({ t, entries, progress, variant, onOpenSheet, onClose }: Props) {
  const list = useRef<HTMLDivElement>(null);
  const live = useRef<Progress>(null);
  const [follow, setFollow] = useState(true);
  const followRef = useRef(true);
  const programmaticAt = useRef(0);
  const shown = variant === "compact" ? entries.slice(-1) : entries;
  const liveOwner = entries.find((entry) => entry.record?.state === "live")?.key ?? null;

  const scrollTo = useCallback((top: number) => {
    const box = list.current;
    if (!box) return;
    programmaticAt.current = performance.now();
    box.scrollTo({ top: Math.max(0, top) });
  }, []);

  /** Keep the current word (or the newest text) in view while following. */
  const keepInView = useCallback(() => {
    const box = list.current;
    if (!box || !followRef.current) return;
    const word = box.querySelector<HTMLElement>(`[data-entry="${live.current?.owner}"] .tw[data-state="current"]`);
    if (!word) {
      scrollTo(box.scrollHeight);
      return;
    }
    const boxRect = box.getBoundingClientRect();
    const rect = word.getBoundingClientRect();
    if (rect.top < boxRect.top + MARGIN || rect.bottom > boxRect.bottom - MARGIN) {
      scrollTo(box.scrollTop + rect.top - boxRect.top - box.clientHeight * 0.35);
    }
  }, [scrollTo]);

  // New entries or streamed text: follow the newest content.
  useEffect(() => {
    if (!live.current) keepInView();
  }, [entries, keepInView]);

  // The live loop: read the voice position every frame, re-light only the words that changed.
  useEffect(() => {
    if (!liveOwner) {
      live.current = null;
      return;
    }
    let frame = 0;
    let applied = "";
    const tick = () => {
      const now = progress();
      if (now && now.owner === liveOwner) {
        live.current = now;
        const key = `${now.litUpTo}:${now.current?.start ?? -1}`;
        const element = list.current?.querySelector(`[data-entry="${liveOwner}"]`);
        if (element && key !== applied) {
          applied = key;
          const view: EntryView = { mode: "lit", litUpTo: now.litUpTo, current: now.current, stopped: false };
          for (const word of element.querySelectorAll<HTMLElement>(".tw")) {
            const state = wordState(view, Number(word.dataset.s), Number(word.dataset.e));
            if (word.dataset.state !== state) word.dataset.state = state;
          }
          keepInView();
        }
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [liveOwner, progress, keepInView]);

  // A scroll the visitor made: away from the end stops following, back near the end resumes.
  function onScroll() {
    const box = list.current;
    if (!box || performance.now() - programmaticAt.current < 250) return;
    const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 48;
    followRef.current = atEnd;
    setFollow(atEnd);
  }

  function jumpToNow() {
    followRef.current = true;
    setFollow(true);
    keepInView();
  }

  // The live entry renders with a constant "pending" word state; the frame loop above lights
  // words directly in the DOM, and React leaves attributes alone until their props change
  // (the entry finishes or stops, which renders the final states).
  const viewOf = (entry: TranscriptEntry): EntryView => entryView(entry.record, null);

  const box =
    variant === "panel"
      ? "transcript-panel flex h-full flex-col rounded-3xl border border-ink-700/70 shadow-[0_30px_80px_-40px_rgba(0,0,0,0.9)]"
      : variant === "sheet"
        ? "transcript-panel fixed inset-x-0 bottom-0 z-40 flex h-[72dvh] flex-col rounded-t-3xl border-t border-ink-700 shadow-[0_-30px_80px_-30px_rgba(0,0,0,0.9)] backdrop-blur-md"
        : "transcript-panel relative flex flex-col rounded-2xl border border-ink-700/70";

  return (
    <section aria-label={t.conversation.transcriptTitle} className={box}>
      {variant !== "compact" && (
        <header className="flex items-center justify-between gap-3 border-b border-ink-800 px-5 py-3">
          <h2 className="eyebrow text-mist-400">{t.conversation.transcriptTitle}</h2>
          {variant === "sheet" && onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label={t.conversation.transcriptClose}
              className="grid size-9 place-items-center rounded-full text-mist-200 transition-colors hover:bg-ink-800 hover:text-mist-50"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </header>
      )}
      <div
        ref={list}
        onScroll={onScroll}
        tabIndex={0}
        aria-label={t.conversation.transcriptTitle}
        className={`min-h-0 flex-1 overflow-y-auto overscroll-contain ${variant === "compact" ? "max-h-[min(9.5rem,22dvh)] px-4 pb-3 pt-4" : "px-5 py-4"}`}
      >
        <ol className="space-y-5">
          {shown.map((entry) => (
            <li key={entry.key}>
              {entry.kind === "answer" && (
                <p dir="auto" className="mb-1.5 text-xs leading-snug text-mist-400">
                  <span className="sr-only">{t.conversation.you}: </span>
                  {entry.question}
                </p>
              )}
              <EntryBody entry={entry} view={viewOf(entry)} t={t} compact={variant === "compact"} />
            </li>
          ))}
        </ol>
      </div>
      {!follow && (
        <button
          type="button"
          onClick={jumpToNow}
          className="absolute bottom-3 start-1/2 z-10 -translate-x-1/2 rounded-full border border-accent/50 bg-ink-900/95 px-3 py-1 text-xs font-medium text-mist-50 shadow-lg backdrop-blur transition-colors hover:border-accent rtl:translate-x-1/2"
        >
          ↓ {t.conversation.jumpToNow}
        </button>
      )}
      {variant === "compact" && onOpenSheet && (
        <button
          type="button"
          onClick={onOpenSheet}
          className="absolute -top-3 end-3 rounded-full border border-ink-700 bg-ink-900 px-2.5 py-0.5 text-[0.7rem] text-mist-200 transition-colors hover:border-accent/60 hover:text-mist-50"
        >
          {t.conversation.transcriptOpen}
        </button>
      )}
    </section>
  );
}

function EntryBody({ entry, view, t, compact }: { entry: TranscriptEntry; view: EntryView; t: Dictionary; compact: boolean }) {
  if (entry.kind === "greeting") {
    return <SpokenText text={entry.text} lang={entry.lang} rtl={entry.rtl} view={view} entryKey={entry.key} />;
  }
  const { answer, errorText } = entry;
  const finished = answer.status !== "streaming";
  const stopped = answer.status === "stopped" || entry.record?.state === "stopped";
  return (
    <>
      {answer.text ? (
        <SpokenText text={answer.text} lang={entry.lang} rtl={entry.rtl} view={view} entryKey={entry.key} />
      ) : (
        !finished && (
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
        )
      )}
      {stopped && <p className="mt-1 text-xs text-mist-400">— {t.conversation.stopped}</p>}
      {errorText && <p className="mt-1 text-sm text-accent">{errorText}</p>}
      {/* The compact phone box keeps to the words; sources are in the full transcript. */}
      {finished && !compact && (
        <div className="[&>div]:justify-start">
          <SourceChips sources={answer.sources} label={t.conversation.sources} />
        </div>
      )}
    </>
  );
}

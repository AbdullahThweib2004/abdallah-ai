"use client";

import { type FormEvent, type Ref, useState } from "react";

import type { VoicePhase } from "@/hooks/useVoice";
import type { Dictionary } from "@/lib/i18n/config";

type Props = {
  t: Dictionary;
  onSend: (text: string) => void;
  /** While an answer streams or is spoken, the send button becomes a Stop button. */
  busy: boolean;
  /** Seconds left of a provider-limit wait: sending and the mic are disabled until 0. */
  waitSeconds?: number;
  onStop: () => void;
  inputRef: Ref<HTMLInputElement>;
  voice: {
    phase: VoicePhase;
    /** Milliseconds left in the last 5 s of a recording, else null. */
    remainingMs: number | null;
    /** A localized notice (mic blocked, nothing heard, …), or null. */
    notice: string | null;
    replies: boolean;
    onToggleMic: () => void;
    onToggleReplies: () => void;
  };
};

export function Composer({ t, onSend, busy, waitSeconds = 0, onStop, inputRef, voice }: Props) {
  const [value, setValue] = useState("");
  const { phase, remainingMs } = voice;
  const listening = phase === "listening";
  const transcribing = phase === "transcribing";
  const waiting = waitSeconds > 0;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || waiting || !value.trim()) return;
    onSend(value);
    setValue("");
  }

  const seconds = remainingMs === null ? null : Math.ceil(remainingMs / 1000);
  const status = voice.notice
    ? voice.notice
    : listening
      ? t.voice.listening + (seconds !== null ? ` ${t.voice.countdown.replace("{s}", String(seconds))}` : "")
      : transcribing
        ? t.voice.transcribing
        : "";
  const showStop = busy || listening || transcribing;

  return (
    <div className="relative">
      <p
        id="voice-status"
        role="status"
        className={`absolute inset-x-0 bottom-full mb-2 text-center text-xs transition-opacity ${
          voice.notice ? "text-accent" : "text-mist-200"
        } ${status ? "opacity-100" : "pointer-events-none opacity-0"}`}
      >
        {status}
        {seconds !== null && (
          <span aria-hidden="true" className="ms-2 inline-grid size-5 place-items-center rounded-full bg-accent font-semibold text-accent-ink tabular-nums">
            {seconds}
          </span>
        )}
      </p>
      <form
        onSubmit={submit}
        className="flex items-center gap-1 rounded-full border border-ink-700 bg-ink-900 p-1.5 ps-5 shadow-[0_20px_60px_-30px_rgba(0,0,0,0.9)] focus-within:border-accent/60 sm:gap-2"
      >
        <label htmlFor="composer-input" className="sr-only">
          {t.conversation.inputLabel}
        </label>
        <input
          id="composer-input"
          ref={inputRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={t.conversation.placeholder}
          autoComplete="off"
          maxLength={500}
          className="min-w-0 flex-1 bg-transparent py-2 text-base text-mist-50 placeholder:text-mist-400 focus:outline-none"
        />
        <button
          type="button"
          onClick={voice.onToggleReplies}
          aria-pressed={voice.replies}
          aria-label={t.voice.replies}
          title={t.voice.replies}
          className={`grid size-10 shrink-0 place-items-center rounded-full transition-colors hover:bg-ink-800 ${
            voice.replies ? "text-accent" : "text-mist-400 hover:text-mist-50"
          }`}
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" />
            {voice.replies ? (
              <path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" />
            ) : (
              <path d="m16 9.5 5 5m0-5-5 5" />
            )}
          </svg>
        </button>
        <button
          type="button"
          onClick={voice.onToggleMic}
          disabled={transcribing || (waiting && !listening)}
          aria-pressed={listening}
          aria-label={listening ? t.voice.micStop : transcribing ? t.voice.micBusy : t.voice.micStart}
          aria-describedby="voice-status voice-privacy"
          title={t.voice.micStart}
          className={`relative grid size-10 shrink-0 place-items-center rounded-full transition-colors disabled:cursor-wait disabled:opacity-50 ${
            listening
              ? "bg-accent text-accent-ink hover:bg-accent-strong"
              : "text-mist-200 hover:bg-ink-800 hover:text-mist-50"
          }`}
        >
          {listening && (
            <span aria-hidden="true" className="absolute inset-0 animate-ping rounded-full bg-accent/40 motion-reduce:hidden" />
          )}
          {transcribing ? (
            <span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-mist-400 border-t-transparent motion-reduce:animate-none" />
          ) : (
            <svg aria-hidden="true" viewBox="0 0 24 24" className="relative size-5" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" />
            </svg>
          )}
        </button>
        {/* One element for both roles so keyboard focus survives the switch. */}
        <button
          type={showStop ? "button" : "submit"}
          onClick={showStop ? onStop : undefined}
          disabled={!showStop && waiting}
          aria-label={showStop ? t.conversation.stop : t.conversation.send}
          className={`grid size-10 shrink-0 place-items-center rounded-full transition-colors disabled:cursor-wait disabled:opacity-50 ${
            showStop
              ? "border border-accent/60 bg-ink-800 text-accent hover:bg-ink-700"
              : "bg-accent text-accent-ink hover:bg-accent-strong"
          }`}
        >
          {showStop ? (
            <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : (
            <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5 rtl:-scale-x-100" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>
      </form>
    </div>
  );
}

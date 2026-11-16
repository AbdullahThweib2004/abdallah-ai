"use client";

import { type FormEvent, type Ref, useEffect, useRef, useState } from "react";

import type { Dictionary } from "@/lib/i18n/config";

const NOTICE_MS = 4000;

type Props = {
  t: Dictionary;
  onSend: (text: string) => void;
  inputRef: Ref<HTMLInputElement>;
};

export function Composer({ t, onSend, inputRef }: Props) {
  const [value, setValue] = useState("");
  const [voiceNotice, setVoiceNotice] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => clearTimeout(timer.current ?? undefined), []);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!value.trim()) return;
    onSend(value);
    setValue("");
  }

  function showVoiceNotice() {
    setVoiceNotice(true);
    clearTimeout(timer.current ?? undefined);
    timer.current = setTimeout(() => setVoiceNotice(false), NOTICE_MS);
  }

  return (
    <div className="relative">
      <p
        id="voice-notice"
        role="status"
        className={`absolute inset-x-0 bottom-full mb-2 text-center text-xs text-accent transition-opacity ${
          voiceNotice ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        {voiceNotice ? t.conversation.voiceSoon : ""}
      </p>
      <form
        onSubmit={submit}
        className="flex items-center gap-2 rounded-full border border-ink-700 bg-ink-900 p-1.5 ps-5 shadow-[0_20px_60px_-30px_rgba(0,0,0,0.9)] focus-within:border-accent/60"
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
          onClick={showVoiceNotice}
          aria-label={t.conversation.mic}
          aria-describedby="voice-notice"
          className="grid size-10 shrink-0 place-items-center rounded-full text-mist-200 transition-colors hover:bg-ink-800 hover:text-mist-50"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" />
          </svg>
        </button>
        <button
          type="submit"
          aria-label={t.conversation.send}
          className="grid size-10 shrink-0 place-items-center rounded-full bg-accent text-accent-ink transition-colors hover:bg-accent-strong"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5 rtl:-scale-x-100" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import {
  GREETING_PLAYED_KEY,
  type PlayResult,
  classifyGesture,
  greetingReducer,
  greetingUrl,
  ignoredKey,
  initialGreeting,
} from "@/lib/voice/greeting";
import type { Alignment } from "@/lib/voice/timing";
import type { ChatLanguage } from "@/services/types";

type Options = {
  /** Voice config loaded and the speaker exists. */
  ready: boolean;
  /** Voice replies are on (the speaker toggle). */
  replies: boolean;
  /** The visitor already asked something (typed, voice or a deep link). */
  conversationStarted: boolean;
  language: ChatLanguage;
  /** The greeting text in each language (the caption; also the browser-voice fallback). */
  texts: Record<ChatLanguage, string>;
  play: (
    url: string,
    text: string,
    language: ChatLanguage,
    viaGesture: boolean,
    onEnd: () => void,
    alignment: Alignment | null,
  ) => Promise<PlayResult>;
};

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * The spoken greeting: autoplay on load, else on the first ordinary gesture (see
 * lib/voice/greeting.ts). Returns the phase, the number of times it started playing (the
 * caption retypes in sync) and `sayHi` for the "Say hi" button.
 */
export function useGreeting({ ready, replies, conversationStarted, language, texts, play }: Options) {
  const [state, dispatch] = useReducer(greetingReducer, initialGreeting);
  const [plays, setPlays] = useState(0);
  const latest = useRef({ language, texts, play });
  // Character timestamps of the static greeting clips (greeting-{en,ar}.json), for the
  // word-by-word highlighting. Small files, fetched once; until then timing is proportional.
  const alignments = useRef<Partial<Record<ChatLanguage, Alignment>>>({});
  useEffect(() => {
    for (const lang of ["en", "ar"] as const) {
      fetch(`/audio/greeting-${lang}.json`)
        .then((response) => (response.ok ? response.json() : null))
        .then((data: { alignment?: Alignment } | null) => {
          if (data?.alignment) alignments.current[lang] = data.alignment;
        })
        .catch(() => undefined);
    }
  }, []);
  useEffect(() => {
    latest.current = { language, texts, play };
  });

  const attempt = useCallback((viaGesture: boolean) => {
    const { language: lang, texts: all, play: start } = latest.current;
    // The language at play time: a switch before the first play changes the greeting.
    const timing = alignments.current[lang] ?? null;
    void start(greetingUrl(lang), all[lang], lang, viaGesture, () => dispatch({ type: "ended" }), timing).then((result) => {
      if (result === "playing") {
        storage()?.setItem(GREETING_PLAYED_KEY, "1");
        setPlays((count) => count + 1);
      }
      dispatch({ type: "result", result });
    });
  }, []);

  // Decide once the speaker exists: muted, already played this visit, or try autoplay.
  useEffect(() => {
    if (!ready || state.phase !== "idle") return;
    const playedThisVisit = storage()?.getItem(GREETING_PLAYED_KEY) === "1";
    dispatch({ type: "load", muted: !replies, playedThisVisit, conversationStarted });
    if (replies && !playedThisVisit && !conversationStarted) attempt(false);
  }, [ready, state.phase, replies, conversationStarted, attempt]);

  // Muting or starting a conversation ends it for this visit (the speaker stops itself).
  useEffect(() => {
    if (!replies) dispatch({ type: "mute" });
  }, [replies]);
  useEffect(() => {
    if (conversationStarted) dispatch({ type: "conversation" });
  }, [conversationStarted]);

  // Waiting for a gesture: the first ordinary click/keypress plays it, inside the handler
  // (Safari only allows audio started in the gesture itself).
  const waiting = state.phase === "waiting";
  useEffect(() => {
    if (!waiting) return;
    function onGesture(event: Event) {
      if (event instanceof KeyboardEvent && ignoredKey(event.key)) return;
      const kind = classifyGesture(event.target instanceof Element ? event.target : null);
      dispatch({ type: "gesture", kind });
      if (kind === "play") attempt(true);
    }
    document.addEventListener("click", onGesture, true);
    document.addEventListener("keydown", onGesture, true);
    return () => {
      document.removeEventListener("click", onGesture, true);
      document.removeEventListener("keydown", onGesture, true);
    };
  }, [waiting, attempt]);

  /** The "Say hi" button (marked data-greeting-ignore, so the document listener skips it). */
  const sayHi = useCallback(() => {
    dispatch({ type: "gesture", kind: "play" });
    attempt(true);
  }, [attempt]);

  return { phase: state.phase, plays, sayHi };
}

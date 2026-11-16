"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AnswerStatus } from "@/hooks/useConversation";
import { type VoiceRepliesPreference, saveVoiceReplies } from "@/lib/voice/preferences";
import { MicError, type MicErrorKind, Recorder, type Recording } from "@/lib/voice/recorder";
import { Speaker, type SpeakerState } from "@/lib/voice/speaker";
import type { ChatLanguage } from "@/services/types";
import { type VoiceConfig, VoiceHttpError, getVoiceConfig, transcribe } from "@/services/voice";

export type VoicePhase = "idle" | "listening" | "transcribing";

export type VoiceNotice =
  | "micDenied"
  | "micMissing"
  | "micUnsupported"
  | "noSpeech"
  | "tooLong"
  | "busy"
  | "sttUnavailable"
  | "noBrowserVoice"
  | "generic";

/** Hooks the conversation calls while an answer streams (see useConversation). */
export type AnswerListener = {
  onAnswerStart: (language: ChatLanguage) => void;
  onToken: (text: string) => void;
  onAnswerEnd: (status: Exclude<AnswerStatus, "streaming">) => void;
};

const NOTICE_MS = 5000;

function micNotice(kind: MicErrorKind): VoiceNotice {
  return ({ denied: "micDenied", missing: "micMissing", unsupported: "micUnsupported", failed: "generic" } as const)[kind];
}

function transcribeNotice(error: unknown): VoiceNotice {
  if (!(error instanceof VoiceHttpError)) return "generic";
  switch (error.code) {
    case "no_speech":
      return "noSpeech";
    case "too_long":
    case "too_large":
      return "tooLong";
    case "rate_limited":
    case "daily_limit":
    case "daily_cap":
      return "busy";
    case "stt_unavailable":
    case null:
      return "sttUnavailable";
    default:
      return "generic";
  }
}

type Options = {
  initialReplies: VoiceRepliesPreference;
  /** Send the transcribed question as the visitor's message. */
  onTranscript: (text: string) => void;
  /** Stop the answer text stream (Stop button, barge-in). */
  onInterrupt: () => void;
};

export function useVoice({ initialReplies, onTranscript, onInterrupt }: Options) {
  const [config, setConfig] = useState<VoiceConfig | null>(null);
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [remainingMs, setRemainingMs] = useState<number | null>(null);
  const [notice, setNotice] = useState<VoiceNotice | null>(null);
  const [speech, setSpeech] = useState<SpeakerState>({ speaking: false, active: false });
  const [replies, setReplies] = useState(initialReplies === "on");

  const recorder = useRef<Recorder | null>(null);
  const speaker = useRef<Speaker | null>(null);
  const preference = useRef(initialReplies);
  const repliesRef = useRef(replies);
  const callbacks = useRef({ onTranscript, onInterrupt });
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const transcribeAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    callbacks.current = { onTranscript, onInterrupt };
    repliesRef.current = replies;
  });

  const showNotice = useCallback((value: VoiceNotice) => {
    setNotice(value);
    clearTimeout(noticeTimer.current ?? undefined);
    noticeTimer.current = setTimeout(() => setNotice(null), NOTICE_MS);
  }, []);

  // Which providers are active decides between the server voice and the browser voice.
  useEffect(() => {
    const controller = new AbortController();
    getVoiceConfig(controller.signal)
      .then(setConfig)
      .catch(() => {
        if (!controller.signal.aborted) {
          setConfig({
            stt: { provider: "none", max_seconds: 30, max_bytes: 0 },
            tts: { provider: "browser", max_chars: 600 },
          });
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!config) return;
    const instance = new Speaker(config.tts.provider === "browser" ? "browser" : "server", {
      onState: setSpeech,
      onBrowserVoiceMissing: () => showNotice("noBrowserVoice"),
    });
    speaker.current = instance;
    return () => {
      instance.dispose();
      if (speaker.current === instance) speaker.current = null;
    };
  }, [config, showNotice]);

  useEffect(
    () => () => {
      recorder.current?.cancel();
      transcribeAbort.current?.abort();
      clearTimeout(noticeTimer.current ?? undefined);
    },
    [],
  );

  /** Call from every click/keypress that may lead to speech (autoplay rules). */
  const unlock = useCallback(() => speaker.current?.unlock(), []);

  const setRepliesOn = useCallback((on: boolean) => {
    preference.current = on ? "on" : "off";
    setReplies(on);
    saveVoiceReplies(on);
    if (!on) speaker.current?.stop();
  }, []);

  const toggleReplies = useCallback(() => {
    unlock();
    setRepliesOn(!repliesRef.current);
  }, [setRepliesOn, unlock]);

  const stopSpeaking = useCallback(() => speaker.current?.stop(), []);

  const handleRecording = useCallback(
    async (recording: Recording) => {
      recorder.current = null;
      if (!recording.heardSpeech || recording.blob.size === 0) {
        setPhase("idle");
        showNotice("noSpeech");
        return;
      }
      setPhase("transcribing");
      const controller = new AbortController();
      transcribeAbort.current = controller;
      try {
        const result = await transcribe(recording.blob, "auto", controller.signal);
        setPhase("idle");
        callbacks.current.onTranscript(result.text);
      } catch (error) {
        if (controller.signal.aborted) return;
        setPhase("idle");
        showNotice(transcribeNotice(error));
      } finally {
        if (transcribeAbort.current === controller) transcribeAbort.current = null;
      }
    },
    [showNotice],
  );

  const toggleMic = useCallback(async () => {
    if (phase === "listening") {
      recorder.current?.stop();
      return;
    }
    if (phase === "transcribing") return;
    unlock();
    // Barge-in: the visitor talks over the answer, so stop the audio and the text stream.
    speaker.current?.stop();
    callbacks.current.onInterrupt();
    if (config?.stt.provider === "none") {
      showNotice("sttUnavailable");
      return;
    }
    // Using the mic counts as choosing voice: replies default to ON unless turned off before.
    if (preference.current === null) setRepliesOn(true);
    setNotice(null);
    setPhase("listening");
    try {
      recorder.current = await Recorder.open({
        onCountdown: setRemainingMs,
        onStop: (recording) => void handleRecording(recording),
      });
    } catch (error) {
      setPhase("idle");
      showNotice(error instanceof MicError ? micNotice(error.kind) : "generic");
    }
  }, [phase, config, unlock, showNotice, setRepliesOn, handleRecording]);

  /** Stop button: abandons a recording or transcription and stops the audio. */
  const cancel = useCallback(() => {
    recorder.current?.cancel();
    recorder.current = null;
    transcribeAbort.current?.abort();
    setPhase("idle");
    speaker.current?.stop();
  }, []);

  const listener = useMemo<AnswerListener>(
    () => ({
      onAnswerStart: (language) => {
        const instance = speaker.current;
        if (!repliesRef.current || !instance?.unlocked) return;
        instance.begin(language);
      },
      onToken: (text) => speaker.current?.push(text),
      onAnswerEnd: (status) => {
        if (status === "stopped") speaker.current?.stop();
        else speaker.current?.end();
      },
    }),
    [],
  );

  /** Live levels for the avatar: the microphone while listening, else the playing audio. */
  const levels = useCallback(
    (): number[] | null => recorder.current?.levels() ?? speaker.current?.levels() ?? null,
    [],
  );

  return {
    phase,
    remainingMs,
    notice,
    speaking: speech.speaking,
    voicing: speech.active,
    replies,
    listener,
    levels,
    unlock,
    toggleMic,
    toggleReplies,
    stopSpeaking,
    cancel,
  };
}

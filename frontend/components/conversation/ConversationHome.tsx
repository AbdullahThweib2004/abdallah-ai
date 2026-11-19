"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AvatarStage } from "@/components/avatar/AvatarStage";
import { type AnswerMessage, type AvatarState, sameCard, useConversation } from "@/hooks/useConversation";
import { useCountdown } from "@/hooks/useCountdown";
import { useGreeting } from "@/hooks/useGreeting";
import { type AnswerListener, useVoice } from "@/hooks/useVoice";
import { busyMessage } from "@/lib/conversation/cooldown";
import { type Dictionary, type Locale } from "@/lib/i18n/config";
import greetingManifest from "@/public/audio/greeting.json";
import type { VoiceRepliesPreference } from "@/lib/voice/preferences";
import type { VoiceRecord } from "@/lib/voice/transcript";
import type { UiAction } from "@/services/types";

import { CardBody, type CardData } from "./CardBody";
import { CardPanel } from "./CardPanel";
import { Composer } from "./Composer";
import { deepLinkFromParams } from "./deepLink";
import { SuggestionChips } from "./SuggestionChips";
import { type TranscriptEntry, TranscriptPanel } from "./TranscriptPanel";

type Props = CardData & {
  t: Dictionary;
  locale: Locale;
  /** The speaker toggle as saved in its cookie (null: never chosen). */
  voiceReplies: VoiceRepliesPreference;
};

/**
 * The greeting caption is the exact text of the static greeting audio (written next to it by
 * backend/app/greeting.py), so what is shown always matches what is spoken, even when the
 * content API is slow or down.
 */
const greetingTexts = { en: greetingManifest.en.text, ar: greetingManifest.ar.text };

export function ConversationHome({ t, locale, profile, projects, contact, voiceReplies }: Props) {
  const answerListener = useRef<AnswerListener | null>(null);
  const conversation = useConversation(projects ?? [], locale, answerListener);
  const { card, cards, messages, lastAssistant, lastUser, streaming } = conversation;
  const { send, stop, showCard, closeCard } = conversation;
  const voice = useVoice({
    initialReplies: voiceReplies,
    onTranscript: (text) => void send(text),
    onInterrupt: stop,
  });
  useEffect(() => {
    answerListener.current = voice.listener;
  }, [voice.listener]);
  // The spoken greeting: static audio, autoplay or first gesture (see hooks/useGreeting.ts).
  const greeting = useGreeting({
    ready: voice.ready,
    replies: voice.replies,
    conversationStarted: lastUser !== undefined && lastUser !== null,
    language: locale,
    texts: greetingTexts,
    play: voice.playGreeting,
    attach: voice.attachGreetingAlignment,
  });
  const [sheetOpen, setSheetOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Deep links (`/?ask=<id>`, `/?card=contact`) are handled once, then removed from the
  // address bar so following the same link again works.
  const query = useSearchParams().toString();
  const handledQuery = useRef<string | null>(null);
  useEffect(() => {
    if (!query) {
      handledQuery.current = null;
      return;
    }
    if (handledQuery.current === query) return;
    handledQuery.current = query;
    window.history.replaceState(null, "", "/");
    const link = deepLinkFromParams(new URLSearchParams(query), projects);
    if (link?.kind === "card") showCard(link.card);
    if (link?.kind === "ask") {
      const question = t.conversation.askAbout.replace("{title}", link.project.title);
      void send(question, { type: "show_project", project_id: link.project.id });
    }
  }, [query, projects, send, showCard, t.conversation.askAbout]);

  // Focus moves into the card when it opens and back to the composer when it closes.
  const previousCard = useRef(card);
  useEffect(() => {
    if (card && card !== previousCard.current) headingRef.current?.focus();
    if (!card && previousCard.current) inputRef.current?.focus();
    previousCard.current = card;
  }, [card]);

  useEffect(() => {
    if (!card && !sheetOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (sheetOpen) setSheetOpen(false);
      else closeCard();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [card, sheetOpen, closeCard]);

  // A provider rate limit on the latest answer: count down, keep the composer disabled meanwhile.
  const waitSeconds = useCountdown(conversation.busyUntil);

  function errorText(answer: AnswerMessage): string | null {
    if (!answer.error) return null;
    if (answer.error.kind === "server") return answer.error.message;
    if (answer.error.kind === "busy") {
      const seconds = answer === lastAssistant ? waitSeconds : 0;
      return seconds > 0 ? busyMessage(t.conversation.errors.busy, locale, seconds) : t.conversation.errors.busyOver;
    }
    return answer.error.kind === "network" ? t.conversation.errors.network : t.conversation.errors.generic;
  }

  /** Typed and voice questions alike; a click/keypress also unlocks audio playback. */
  function ask(text: string) {
    voice.unlock();
    void send(text);
  }

  function stopAll() {
    stop();
    voice.cancel();
  }

  // Voice phases take over the avatar: listening, transcribing (thinking), and while an
  // answer is voiced: thinking until its audio starts, speaking while audio plays.
  const avatar: AvatarState =
    voice.phase === "listening"
      ? "listening"
      : voice.phase === "transcribing"
        ? "thinking"
        : voice.speaking
          ? "speaking"
          : voice.voicing
            ? "thinking"
            : conversation.avatar;

  const cardOpen = card !== null;
  const projectOf = (action: UiAction | undefined) =>
    action?.type === "show_project" ? projects?.find((project) => project.id === action.project_id) : undefined;
  const cardProject = projectOf(card ?? undefined);
  // Two cards from one answer (e.g. a comparison): offer the one not shown.
  const otherCard = card ? cards.find((option) => !sameCard(option, card)) : undefined;
  const otherProject = projectOf(otherCard);
  // On mobile the card is a bottom sheet; everything except the avatar sits underneath it.
  const underSheet = cardOpen ? "max-lg:hidden" : "";

  // The transcript: the greeting first, then every answer under its question. Each entry's
  // record says what the voice did with it (live / done / stopped; none = not voiced: bright).
  const greetingVoice = voice.records.greeting;
  const greetingRecord: VoiceRecord | undefined =
    greetingVoice?.state === "live" || greetingVoice?.state === "stopped"
      ? greetingVoice
      : !voice.replies || greeting.phase === "done"
        ? undefined
        : { state: "pending" }; // waiting to be spoken: dimmed, still readable
  const entries: TranscriptEntry[] = [
    { kind: "greeting", key: "greeting", text: greetingTexts[locale], lang: locale, rtl: locale === "ar", record: greetingRecord },
  ];
  let question = "";
  for (const message of messages) {
    if (message.role === "user") question = message.text;
    else if (message.kind === "answer") {
      const language = message.language ?? locale;
      entries.push({
        kind: "answer",
        key: `answer:${message.id}`,
        question,
        answer: message,
        lang: language,
        rtl: language === "ar",
        record: voice.records[`answer:${message.id}`],
        errorText: errorText(message),
      });
    }
  }
  // Screen readers get each finished answer once, as a whole.
  const lastFinished = messages.findLast(
    (message): message is AnswerMessage => message.role === "assistant" && message.kind === "answer" && message.status !== "streaming",
  );
  const announcement = lastFinished
    ? [lastFinished.text, lastFinished.status === "stopped" ? `(${t.conversation.stopped})` : "", errorText(lastFinished) ?? ""]
        .filter(Boolean)
        .join(" ")
    : "";

  return (
    <div
      className="relative flex h-[calc(100dvh-var(--header-height))] overflow-hidden"
      style={{
        ["--panel-width" as string]: "min(36vw, 500px)",
        ["--transcript-width" as string]: "clamp(17rem, 25vw, 22.5rem)",
      }}
    >
      {/* Desktop / tablet: the transcript on the start side (left in English, right in Arabic),
          opposite the card panel. */}
      <div className="hidden w-[var(--transcript-width)] shrink-0 py-4 ps-4 min-[769px]:block">
        <TranscriptPanel t={t} entries={entries} progress={voice.progress} variant="panel" />
      </div>

      <section
        aria-label={t.conversation.regionLabel}
        aria-busy={streaming}
        className={`stage-shift flex h-full min-w-0 flex-1 flex-col ${cardOpen ? "max-lg:pb-[58dvh] lg:pe-[calc(var(--panel-width)+2rem)]" : ""}`}
      >
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-6">
          <div className="avatar-frame relative grid min-h-0 flex-1 place-items-center">
            <AvatarStage
              state={avatar}
              label={`${t.avatar.label}: ${t.avatar.states[avatar]}`}
              levels={voice.levels}
              cardOpen={cardOpen}
              rtl={locale === "ar"}
            />
            {greeting.phase === "waiting" && (
              <button
                type="button"
                onClick={greeting.sayHi}
                data-greeting-ignore
                aria-label={t.voice.sayHiLabel}
                className="absolute bottom-1 start-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full border border-accent/40 bg-ink-900/85 py-1.5 ps-1.5 pe-4 text-sm font-medium text-mist-50 shadow-[0_10px_40px_-12px_rgba(245,166,35,0.45)] backdrop-blur transition-colors hover:border-accent hover:bg-ink-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent rtl:translate-x-1/2"
              >
                <span aria-hidden="true" className="relative grid size-7 place-items-center rounded-full bg-accent text-accent-ink">
                  <span className="absolute inset-0 rounded-full bg-accent/50 motion-safe:animate-ping" />
                  <svg viewBox="0 0 16 16" className="relative size-3.5" fill="currentColor">
                    <path d="M4.5 2.8v10.4c0 .6.7 1 1.2.6l7.6-5.2a.7.7 0 0 0 0-1.2L5.7 2.2c-.5-.4-1.2 0-1.2.6Z" />
                  </svg>
                </span>
                <span lang={locale}>{t.voice.sayHi}</span>
              </button>
            )}
          </div>

          <div className={`shrink-0 space-y-3 pt-3 ${underSheet}`}>
            {/* Phones: the current entry under the robot; the full transcript opens as a sheet. */}
            <div className="mt-2 min-[769px]:hidden">
              <TranscriptPanel
                t={t}
                entries={entries}
                progress={voice.progress}
                variant="compact"
                onOpenSheet={() => setSheetOpen(true)}
              />
            </div>

            {!lastUser && (
              <SuggestionChips
                label={t.conversation.suggestionsLabel}
                suggestions={t.conversation.suggestions}
                onPick={ask}
              />
            )}

            <Composer
              t={t}
              onSend={ask}
              busy={streaming || voice.voicing}
              waitSeconds={waitSeconds}
              onStop={stopAll}
              inputRef={inputRef}
              voice={{
                phase: voice.phase,
                remainingMs: voice.remainingMs,
                notice: voice.notice ? t.voice.notices[voice.notice] : null,
                replies: voice.replies,
                onToggleMic: () => void voice.toggleMic(),
                onToggleReplies: voice.toggleReplies,
              }}
            />

            <p className="text-center text-xs text-mist-400">
              {t.conversation.transparency} <span id="voice-privacy">{t.voice.privacy}</span>
            </p>
          </div>
        </div>
      </section>

      {sheetOpen && (
        <div className="min-[769px]:hidden">
          <TranscriptPanel
            t={t}
            entries={entries}
            progress={voice.progress}
            variant="sheet"
            onClose={() => setSheetOpen(false)}
          />
        </div>
      )}

      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {card && (
        <CardPanel
          eyebrow={t.cards.eyebrows[card.type]}
          heading={cardProject?.title ?? t.cards.titles[card.type]}
          headingLang={cardProject ? "en" : undefined}
          closeLabel={t.cards.close}
          onClose={closeCard}
          headingRef={headingRef}
          alternative={
            otherCard && {
              // Short project name: "Nawa: Neural Network …" → "Nawa".
              label: otherProject ? otherProject.title.split(/[:(]/)[0].trim() : t.cards.titles[otherCard.type],
              lang: otherProject ? "en" : undefined,
              switchLabel: t.cards.switchTo,
              onSelect: () => showCard(otherCard),
            }
          }
        >
          <CardBody card={card} data={{ profile, projects, contact }} t={t} />
        </CardPanel>
      )}
    </div>
  );
}

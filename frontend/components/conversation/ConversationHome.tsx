"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AvatarStage } from "@/components/avatar/AvatarStage";
import { type AnswerMessage, type AvatarState, type Message, useConversation } from "@/hooks/useConversation";
import { type AnswerListener, useVoice } from "@/hooks/useVoice";
import { type Dictionary, type Locale, directionOf } from "@/lib/i18n/config";
import type { VoiceRepliesPreference } from "@/lib/voice/preferences";

import { AnswerSubtitle } from "./AnswerSubtitle";
import { CardBody, type CardData } from "./CardBody";
import { CardPanel } from "./CardPanel";
import { Composer } from "./Composer";
import { deepLinkFromParams } from "./deepLink";
import { Subtitle } from "./Subtitle";
import { SuggestionChips } from "./SuggestionChips";
import { Transcript } from "./Transcript";

type Props = CardData & {
  t: Dictionary;
  locale: Locale;
  portraitSrc: string | null;
  /** The speaker toggle as saved in its cookie (null: never chosen). */
  voiceReplies: VoiceRepliesPreference;
};

export function ConversationHome({ t, locale, profile, projects, contact, portraitSrc, voiceReplies }: Props) {
  const answerListener = useRef<AnswerListener | null>(null);
  const conversation = useConversation(projects ?? [], locale, answerListener);
  const { card, messages, lastAssistant, lastUser, streaming } = conversation;
  const { send, stop, showCard, closeCard, spoken } = conversation;
  const voice = useVoice({
    initialReplies: voiceReplies,
    onTranscript: (text) => void send(text),
    onInterrupt: stop,
  });
  useEffect(() => {
    answerListener.current = voice.listener;
  }, [voice.listener]);
  const [historyOpen, setHistoryOpen] = useState(false);
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
    if (!card && !historyOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (historyOpen) setHistoryOpen(false);
      else closeCard();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [card, historyOpen, closeCard]);

  function errorText(answer: AnswerMessage): string | null {
    if (!answer.error) return null;
    if (answer.error.kind === "server") return answer.error.message;
    return answer.error.kind === "network" ? t.conversation.errors.network : t.conversation.errors.generic;
  }

  function assistantText(message: Extract<Message, { role: "assistant" }>): string {
    if (message.kind === "greeting") {
      return (locale === "ar" ? profile?.intro.ar : profile?.intro.en) ?? t.tagline;
    }
    const suffix = message.status === "stopped" ? ` (${t.conversation.stopped})` : "";
    return [message.text + suffix, errorText(message)].filter(Boolean).join(" ") || "…";
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
  const cardProject =
    card?.type === "show_project" ? projects?.find((project) => project.id === card.project_id) : undefined;
  // On mobile the card is a bottom sheet; everything except the avatar sits underneath it.
  const underSheet = cardOpen ? "max-lg:hidden" : "";

  return (
    <div
      className="relative h-[calc(100dvh-var(--header-height))] overflow-hidden"
      style={{ ["--panel-width" as string]: "min(42vw, 540px)" }}
    >
      <section
        aria-label={t.conversation.regionLabel}
        aria-busy={streaming}
        className={`stage-shift flex h-full flex-col ${cardOpen ? "max-lg:pb-[58dvh] lg:pe-[calc(var(--panel-width)+2rem)]" : ""}`}
      >
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-6">
          <div className="avatar-frame grid min-h-0 flex-1 place-items-center">
            <AvatarStage
              state={avatar}
              portraitSrc={portraitSrc}
              label={`${t.avatar.label}: ${t.avatar.states[avatar]}`}
              levels={voice.levels}
            />
          </div>

          <div className={`shrink-0 space-y-4 pt-4 ${underSheet}`}>
            {lastAssistant?.role === "assistant" && lastAssistant.kind === "greeting" && (
              <Subtitle
                key={`greeting-${locale}`}
                text={assistantText(lastAssistant)}
                lang={locale}
                dir={directionOf(locale)}
                onDone={spoken}
              />
            )}
            {lastAssistant?.role === "assistant" && lastAssistant.kind === "answer" && (
              <AnswerSubtitle
                answer={lastAssistant}
                errorText={errorText(lastAssistant)}
                t={t}
                fallbackLang={locale}
              />
            )}

            {!lastUser && (
              <SuggestionChips
                label={t.conversation.suggestionsLabel}
                suggestions={t.conversation.suggestions}
                onPick={ask}
              />
            )}

            <Transcript
              t={t}
              messages={messages}
              lastUser={lastUser}
              assistantText={assistantText}
              open={historyOpen}
              onToggle={() => setHistoryOpen((value) => !value)}
              rtl={locale === "ar"}
            />

            <Composer
              t={t}
              onSend={ask}
              busy={streaming || voice.voicing}
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

      {card && (
        <CardPanel
          eyebrow={t.cards.eyebrows[card.type]}
          heading={cardProject?.title ?? t.cards.titles[card.type]}
          headingLang={cardProject ? "en" : undefined}
          closeLabel={t.cards.close}
          onClose={closeCard}
          headingRef={headingRef}
        >
          <CardBody card={card} data={{ profile, projects, contact }} t={t} />
        </CardPanel>
      )}
    </div>
  );
}

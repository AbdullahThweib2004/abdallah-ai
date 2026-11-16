"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AvatarStage } from "@/components/avatar/AvatarStage";
import { type Message, useConversation } from "@/hooks/useConversation";
import { type Dictionary, type Locale, directionOf } from "@/lib/i18n/config";

import { CardBody, type CardData } from "./CardBody";
import { CardPanel } from "./CardPanel";
import { Composer } from "./Composer";
import { actionFromParams } from "./deepLink";
import { Subtitle } from "./Subtitle";
import { SuggestionChips } from "./SuggestionChips";
import { Transcript } from "./Transcript";

type Props = CardData & {
  t: Dictionary;
  locale: Locale;
  portraitSrc: string | null;
};

export function ConversationHome({ t, locale, profile, projects, contact, portraitSrc }: Props) {
  const conversation = useConversation(projects ?? []);
  const { card, messages, lastAssistant, lastUser, avatar, send, open, closeCard, spoken } = conversation;
  const [historyOpen, setHistoryOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Deep links (`/?ask=<id>`, `/?card=contact`): applied once per distinct query string,
  // then removed from the address bar so the same link works again later.
  const searchParams = useSearchParams();
  const query = searchParams.toString();
  const [appliedQuery, setAppliedQuery] = useState("");
  if (query !== appliedQuery) {
    setAppliedQuery(query);
    const action = actionFromParams(new URLSearchParams(query), projects);
    if (action) open(action.card, action.kind);
  }
  useEffect(() => {
    if (appliedQuery) window.history.replaceState(null, "", "/");
  }, [appliedQuery]);

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

  function assistantText(message: Extract<Message, { role: "assistant" }>): string {
    if (message.kind === "greeting") {
      return (locale === "ar" ? profile?.intro.ar : profile?.intro.en) ?? t.tagline;
    }
    return t.conversation.replies[message.kind];
  }

  const showChips = !lastUser || lastAssistant?.role !== "assistant" || lastAssistant.kind === "noMatch";
  const subtitle = lastAssistant?.role === "assistant" ? lastAssistant : null;
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
        className={`stage-shift flex h-full flex-col ${cardOpen ? "max-lg:pb-[58dvh] lg:pe-[calc(var(--panel-width)+2rem)]" : ""}`}
      >
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-6">
          <div className="avatar-frame grid min-h-0 flex-1 place-items-center">
            <AvatarStage
              state={avatar}
              portraitSrc={portraitSrc}
              label={`${t.avatar.label}: ${t.avatar.states[avatar]}`}
            />
          </div>

          <div className={`shrink-0 space-y-4 pt-4 ${underSheet}`}>
            {subtitle && (
              <Subtitle
                key={`${subtitle.id}-${locale}`}
                text={assistantText(subtitle)}
                lang={locale}
                dir={directionOf(locale)}
                onDone={spoken}
              />
            )}

            {showChips && (
              <SuggestionChips
                label={t.conversation.suggestionsLabel}
                suggestions={t.conversation.suggestions}
                onPick={send}
              />
            )}

            <Transcript
              t={t}
              messages={messages}
              lastUser={lastUser}
              assistantText={assistantText}
              open={historyOpen}
              onToggle={() => setHistoryOpen((value) => !value)}
            />

            <Composer t={t} onSend={send} inputRef={inputRef} />

            <p className="text-center text-xs text-mist-400">{t.conversation.transparency}</p>
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

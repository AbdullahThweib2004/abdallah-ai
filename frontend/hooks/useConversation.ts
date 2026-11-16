"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

import { matchIntent } from "@/lib/conversation/localIntentStub";
import type { ProjectSummary, UiAction } from "@/services/types";

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

/**
 * Assistant messages are stored as kinds, not text, so they re-render in the current UI
 * language. Until step 4 the assistant only ever says these fixed, honest messages.
 */
export type AssistantKind = "greeting" | "related" | "noMatch" | "askProject";

export type Message =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; kind: AssistantKind };

type State = {
  messages: Message[];
  avatar: AvatarState;
  card: UiAction | null;
  nextId: number;
};

type Event =
  | { type: "user"; text: string }
  | { type: "reply"; kind: AssistantKind; card: UiAction | null }
  | { type: "showCard"; card: UiAction }
  | { type: "spoken" }
  | { type: "closeCard" };

const THINKING_MS = 700;

function reducer(state: State, event: Event): State {
  switch (event.type) {
    case "user":
      return {
        ...state,
        messages: [...state.messages, { id: state.nextId, role: "user", text: event.text }],
        nextId: state.nextId + 1,
        avatar: "thinking",
      };
    case "reply":
      return {
        ...state,
        messages: [...state.messages, { id: state.nextId, role: "assistant", kind: event.kind }],
        nextId: state.nextId + 1,
        avatar: "speaking",
        card: event.card,
      };
    case "showCard":
      return { ...state, card: event.card };
    case "spoken":
      return state.avatar === "speaking" ? { ...state, avatar: "idle" } : state;
    case "closeCard":
      return { ...state, card: null };
  }
}

const INITIAL: State = {
  messages: [{ id: 0, role: "assistant", kind: "greeting" }],
  avatar: "speaking", // the greeting "speaks" while its subtitle types in
  card: null,
  nextId: 1,
};

export function useConversation(projects: ProjectSummary[]) {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => clearTimeout(timer.current ?? undefined), []);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      dispatch({ type: "user", text: trimmed });
      clearTimeout(timer.current ?? undefined);
      timer.current = setTimeout(() => {
        const action = matchIntent(trimmed, projects);
        dispatch({ type: "reply", kind: action ? "related" : "noMatch", card: action });
      }, THINKING_MS);
    },
    [projects],
  );

  /**
   * Open a card directly, for deep links such as `/?ask=<id>` (with a short fixed message)
   * or `/?card=contact` (card only).
   */
  const open = useCallback((card: UiAction, kind?: AssistantKind) => {
    dispatch(kind ? { type: "reply", kind, card } : { type: "showCard", card });
  }, []);

  const closeCard = useCallback(() => dispatch({ type: "closeCard" }), []);
  const spoken = useCallback(() => dispatch({ type: "spoken" }), []);

  const lastAssistant = [...state.messages].reverse().find((m) => m.role === "assistant");
  const lastUser = [...state.messages].reverse().find((m) => m.role === "user");

  return { ...state, lastAssistant, lastUser, send, open, closeCard, spoken };
}

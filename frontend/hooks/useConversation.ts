"use client";

import { type RefObject, useCallback, useEffect, useReducer, useRef } from "react";

import type { AnswerListener } from "@/hooks/useVoice";

import { cooldownUntil } from "@/lib/conversation/cooldown";
import { ChatHttpError, streamChat } from "@/services/chatStream";
import type { ChatLanguage, ChatSource, ChatTurn, ProjectSummary, UiAction } from "@/services/types";

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

export type AnswerStatus = "streaming" | "done" | "stopped" | "error";

export type AnswerError =
  | { kind: "server"; message: string } // friendly text from the API (already localized)
  | { kind: "network" } // no usable response; the UI shows its own message
  | { kind: "generic" }
  // A provider rate limit: the UI counts down to `until` (ms since epoch), then allows asking.
  | { kind: "busy"; until: number };

export type Message =
  | { id: number; role: "user"; text: string }
  // The greeting is stored as a kind so it re-renders in the current UI language.
  | { id: number; role: "assistant"; kind: "greeting" }
  | {
      id: number;
      role: "assistant";
      kind: "answer";
      text: string;
      status: AnswerStatus;
      language: ChatLanguage | null;
      error: AnswerError | null;
      sources: ChatSource[];
    };

export type AnswerMessage = Extract<Message, { kind: "answer" }>;

/**
 * `card` is the open card; `cards` are the cards the AI requested for the latest answer (0–2),
 * so the panel can offer the other one ("+1").
 */
type State = { messages: Message[]; avatar: AvatarState; card: UiAction | null; cards: UiAction[] };

type Event =
  | { type: "ask"; userId: number; answerId: number; text: string; card: UiAction | null }
  | { type: "start"; id: number; language: ChatLanguage }
  | { type: "actions"; actions: UiAction[] }
  | { type: "token"; id: number; text: string }
  | {
      type: "finish";
      id: number;
      status: Exclude<AnswerStatus, "streaming">;
      error?: AnswerError;
      sources?: ChatSource[];
    }
  | { type: "showCard"; card: UiAction }
  | { type: "spoken" }
  | { type: "closeCard" };

/** The API accepts at most 8 previous turns of at most 2000 characters each. */
const MAX_HISTORY_TURNS = 8;
const MAX_TURN_CHARS = 2000;

function updateAnswer(state: State, id: number, change: (m: AnswerMessage) => AnswerMessage): Message[] {
  return state.messages.map((m) => (m.id === id && m.role === "assistant" && m.kind === "answer" ? change(m) : m));
}

function reducer(state: State, event: Event): State {
  switch (event.type) {
    case "ask":
      return {
        messages: [
          ...state.messages,
          { id: event.userId, role: "user", text: event.text },
          {
            id: event.answerId,
            role: "assistant",
            kind: "answer",
            text: "",
            status: "streaming",
            language: null,
            error: null,
            sources: [],
          },
        ],
        avatar: "thinking", // until the first token
        card: event.card ?? state.card,
        cards: event.card ? [event.card] : state.cards,
      };
    case "start":
      return { ...state, messages: updateAnswer(state, event.id, (m) => ({ ...m, language: event.language })) };
    case "actions":
      // No card requested (small talk, refusals): keep whatever is open.
      return event.actions.length ? { ...state, card: event.actions[0], cards: event.actions } : state;
    case "token":
      return {
        ...state,
        avatar: "speaking",
        messages: updateAnswer(state, event.id, (m) => ({ ...m, text: m.text + event.text })),
      };
    case "finish":
      return {
        ...state,
        avatar: "idle",
        messages: updateAnswer(state, event.id, (m) =>
          m.status === "streaming"
            ? { ...m, status: event.status, error: event.error ?? null, sources: event.sources ?? [] }
            : m,
        ),
      };
    case "showCard":
      // Switching between the AI's cards keeps the pair; any other card replaces it.
      return {
        ...state,
        card: event.card,
        cards: state.cards.some((card) => sameCard(card, event.card)) ? state.cards : [event.card],
      };
    case "spoken":
      return state.avatar === "speaking" ? { ...state, avatar: "idle" } : state;
    case "closeCard":
      return { ...state, card: null, cards: [] };
  }
}

const INITIAL: State = {
  messages: [{ id: 0, role: "assistant", kind: "greeting" }],
  avatar: "speaking", // the greeting "speaks" while its subtitle types in
  card: null,
  cards: [],
};

export function sameCard(a: UiAction, b: UiAction): boolean {
  return a.type === b.type && (a.type !== "show_project" || (b.type === "show_project" && a.project_id === b.project_id));
}

const CARD_TYPES = new Set<UiAction["type"]>([
  "show_project",
  "show_projects",
  "show_skills",
  "show_experience",
  "show_education",
  "show_contact",
]);

/**
 * The server already validated these against its allowlist; check again against what this
 * page knows (defense in depth), so an unknown type or project id can never open anything.
 */
function knownActions(actions: unknown, projects: ProjectSummary[]): UiAction[] {
  if (!Array.isArray(actions)) return [];
  const known: UiAction[] = [];
  for (const action of actions as UiAction[]) {
    if (typeof action !== "object" || action === null || !CARD_TYPES.has(action.type)) continue;
    if (action.type === "show_project" && !projects.some((project) => project.id === action.project_id)) continue;
    if (known.some((card) => sameCard(card, action))) continue;
    known.push(action.type === "show_project" ? { type: "show_project", project_id: action.project_id } : { type: action.type });
  }
  return known.slice(0, 2);
}

/** The last turns the model may see: visitor messages and finished (or stopped) answers. */
function historyOf(messages: Message[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  for (const m of messages) {
    if (m.role === "user") turns.push({ role: "user", content: m.text.slice(0, MAX_TURN_CHARS) });
    else if (m.kind === "answer" && m.text.trim() && m.status !== "error") {
      turns.push({ role: "assistant", content: m.text.trim().slice(0, MAX_TURN_CHARS) });
    }
  }
  return turns.slice(-MAX_HISTORY_TURNS);
}

/**
 * `listener` (optional) follows each answer as it streams; the voice layer uses it to speak
 * sentences as soon as they are complete.
 */
export function useConversation(
  projects: ProjectSummary[],
  uiLanguage: ChatLanguage,
  listener?: RefObject<AnswerListener | null>,
) {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const messagesRef = useRef(state.messages);
  const nextId = useRef(1);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    messagesRef.current = state.messages;
  }, [state.messages]);
  useEffect(() => () => abort.current?.abort(), []);

  const streaming = state.messages.some((m) => m.role === "assistant" && m.kind === "answer" && m.status === "streaming");

  /**
   * Ask a question. Cards open when the server sends validated AI actions; a caller may also
   * open one right away (deep links, whose ids were validated before).
   */
  const send = useCallback(
    async (text: string, card?: UiAction) => {
      const message = text.trim();
      if (!message || abort.current) return;
      // Still counting down after a provider limit (the composer is disabled; this also
      // covers a voice question finishing during the wait).
      const last = messagesRef.current.findLast((m) => m.role === "assistant");
      if (last?.role === "assistant" && last.kind === "answer" && last.error?.kind === "busy" && Date.now() < last.error.until) {
        return;
      }
      const history = historyOf(messagesRef.current);
      const userId = nextId.current++;
      const id = nextId.current++;
      dispatch({ type: "ask", userId, answerId: id, text: message, card: card ?? null });

      const controller = new AbortController();
      abort.current = controller;
      let status: Exclude<AnswerStatus, "streaming"> = "error";
      try {
        for await (const event of streamChat({ message, history, ui_language: uiLanguage }, controller.signal)) {
          if (event.type === "start") {
            dispatch({ type: "start", id, language: event.language });
            listener?.current?.onAnswerStart(event.language, id);
          } else if (event.type === "action") {
            // Arrives before the first token, so the card opens while the answer is spoken.
            dispatch({ type: "actions", actions: knownActions(event.actions, projects) });
          } else if (event.type === "token") {
            dispatch({ type: "token", id, text: event.text });
            listener?.current?.onToken(event.text);
          } else if (event.type === "done") {
            status = "done";
            dispatch({ type: "finish", id, status: "done", sources: event.sources });
          } else if (event.type === "error") {
            const error: AnswerError =
              event.code === "busy" && typeof event.retry_after === "number"
                ? { kind: "busy", until: cooldownUntil(event.retry_after, Date.now()) }
                : { kind: "server", message: event.message };
            dispatch({ type: "finish", id, status: "error", error });
          }
        }
        // A stream that ends without `done`/`error` was cut off.
        dispatch({ type: "finish", id, status: "error", error: { kind: "network" } });
      } catch (error) {
        if (controller.signal.aborted) {
          status = "stopped";
          dispatch({ type: "finish", id, status: "stopped" });
        } else if (error instanceof ChatHttpError) {
          dispatch({
            type: "finish",
            id,
            status: "error",
            error: error.detail ? { kind: "server", message: error.detail } : { kind: "generic" },
          });
        } else dispatch({ type: "finish", id, status: "error", error: { kind: "network" } });
      } finally {
        if (abort.current === controller) abort.current = null;
        // Speak what arrived, even after an error; a stopped answer goes silent.
        listener?.current?.onAnswerEnd(status);
      }
    },
    [projects, uiLanguage, listener],
  );

  const stop = useCallback(() => abort.current?.abort(), []);
  const showCard = useCallback((card: UiAction) => dispatch({ type: "showCard", card }), []);
  const closeCard = useCallback(() => dispatch({ type: "closeCard" }), []);
  const spoken = useCallback(() => dispatch({ type: "spoken" }), []);

  const lastAssistant = state.messages.findLast((m) => m.role === "assistant");
  const lastUser = state.messages.findLast((m) => m.role === "user");

  // The end of the current provider-limit wait, if the latest answer hit one.
  const busyUntil =
    lastAssistant?.role === "assistant" && lastAssistant.kind === "answer" && lastAssistant.error?.kind === "busy"
      ? lastAssistant.error.until
      : null;

  return { ...state, streaming, busyUntil, lastAssistant, lastUser, send, stop, showCard, closeCard, spoken };
}

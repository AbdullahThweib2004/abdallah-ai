"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

import { matchIntent } from "@/lib/conversation/localIntentStub";
import { ChatHttpError, streamChat } from "@/services/chatStream";
import type { ChatLanguage, ChatTurn, ProjectSummary, UiAction } from "@/services/types";

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

export type AnswerStatus = "streaming" | "done" | "stopped" | "error";

export type AnswerError =
  | { kind: "server"; message: string } // friendly text from the API (already localized)
  | { kind: "network" } // no usable response; the UI shows its own message
  | { kind: "generic" };

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
    };

export type AnswerMessage = Extract<Message, { kind: "answer" }>;

type State = { messages: Message[]; avatar: AvatarState; card: UiAction | null };

type Event =
  | { type: "ask"; userId: number; answerId: number; text: string; card: UiAction | null }
  | { type: "start"; id: number; language: ChatLanguage }
  | { type: "token"; id: number; text: string }
  | { type: "finish"; id: number; status: Exclude<AnswerStatus, "streaming">; error?: AnswerError }
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
          },
        ],
        avatar: "thinking", // until the first token
        card: event.card ?? state.card,
      };
    case "start":
      return { ...state, messages: updateAnswer(state, event.id, (m) => ({ ...m, language: event.language })) };
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
          m.status === "streaming" ? { ...m, status: event.status, error: event.error ?? null } : m,
        ),
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
};

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

export function useConversation(projects: ProjectSummary[], uiLanguage: ChatLanguage) {
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
   * Ask a question. The card comes from the TEMPORARY keyword stub (step 6 replaces it with
   * validated AI actions) unless the caller passes one explicitly.
   */
  const send = useCallback(
    async (text: string, card?: UiAction) => {
      const message = text.trim();
      if (!message || abort.current) return;
      const history = historyOf(messagesRef.current);
      const userId = nextId.current++;
      const id = nextId.current++;
      dispatch({ type: "ask", userId, answerId: id, text: message, card: card ?? matchIntent(message, projects) });

      const controller = new AbortController();
      abort.current = controller;
      try {
        for await (const event of streamChat({ message, history, ui_language: uiLanguage }, controller.signal)) {
          if (event.type === "start") dispatch({ type: "start", id, language: event.language });
          else if (event.type === "token") dispatch({ type: "token", id, text: event.text });
          else if (event.type === "done") dispatch({ type: "finish", id, status: "done" });
          else if (event.type === "error") {
            dispatch({ type: "finish", id, status: "error", error: { kind: "server", message: event.message } });
          }
        }
        // A stream that ends without `done`/`error` was cut off.
        dispatch({ type: "finish", id, status: "error", error: { kind: "network" } });
      } catch (error) {
        if (controller.signal.aborted) dispatch({ type: "finish", id, status: "stopped" });
        else if (error instanceof ChatHttpError) {
          dispatch({
            type: "finish",
            id,
            status: "error",
            error: error.detail ? { kind: "server", message: error.detail } : { kind: "generic" },
          });
        } else dispatch({ type: "finish", id, status: "error", error: { kind: "network" } });
      } finally {
        if (abort.current === controller) abort.current = null;
      }
    },
    [projects, uiLanguage],
  );

  const stop = useCallback(() => abort.current?.abort(), []);
  const showCard = useCallback((card: UiAction) => dispatch({ type: "showCard", card }), []);
  const closeCard = useCallback(() => dispatch({ type: "closeCard" }), []);
  const spoken = useCallback(() => dispatch({ type: "spoken" }), []);

  const lastAssistant = state.messages.findLast((m) => m.role === "assistant");
  const lastUser = state.messages.findLast((m) => m.role === "user");

  return { ...state, streaming, lastAssistant, lastUser, send, stop, showCard, closeCard, spoken };
}

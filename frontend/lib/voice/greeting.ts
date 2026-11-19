/**
 * The spoken greeting on a first visit (static files, see backend/app/greeting.py).
 *
 * Browsers block audio until a user gesture, so: on load the greeting TRIES to autoplay; if
 * that is blocked it WAITS and plays on the first gesture anywhere on the page, except gestures
 * that start their own flow (the composer: typing, send, mic, the speaker toggle; the suggestion
 * chips), which cancel it. Links and the language switcher are ignored (navigation; the next
 * play simply uses the new language). Muting cancels it; it plays at most once per visit.
 */

export type GreetingPhase =
  /** Not decided yet (voice config loading). */
  | "idle"
  /** play() in progress (autoplay on load, or inside a gesture). */
  | "trying"
  /** Autoplay was blocked: the "Say hi" button shows, the next gesture plays it. */
  | "waiting"
  | "playing"
  /** Played, muted, cancelled, or already played this visit: never again. */
  | "done";

export type PlayResult = "playing" | "blocked" | "failed";

export type GreetingState = { phase: GreetingPhase; viaGesture: boolean };

export type GreetingEvent =
  | { type: "load"; muted: boolean; playedThisVisit: boolean; conversationStarted: boolean }
  | { type: "gesture"; kind: GestureKind }
  | { type: "result"; result: PlayResult }
  | { type: "ended" }
  | { type: "mute" }
  | { type: "conversation" };

export type GestureKind = "play" | "cancel" | "ignore";

export const initialGreeting: GreetingState = { phase: "idle", viaGesture: false };

export function greetingReducer(state: GreetingState, event: GreetingEvent): GreetingState {
  if (state.phase === "done") return state;
  switch (event.type) {
    case "load":
      if (state.phase !== "idle") return state;
      if (event.muted || event.playedThisVisit || event.conversationStarted) return done;
      return { phase: "trying", viaGesture: false };
    case "gesture":
      if (state.phase !== "waiting" || event.kind === "ignore") return state;
      return event.kind === "cancel" ? done : { phase: "trying", viaGesture: true };
    case "result":
      if (state.phase !== "trying") return state;
      if (event.result === "playing") return { phase: "playing", viaGesture: state.viaGesture };
      // Blocked on load, or the file failed on load: wait for a gesture (the browser-voice
      // fallback also needs one). Failing inside a gesture: give up.
      return state.viaGesture ? done : { phase: "waiting", viaGesture: false };
    case "ended":
      return state.phase === "playing" ? done : state;
    case "mute":
    case "conversation":
      return done;
  }
}

const done: GreetingState = { phase: "done", viaGesture: false };

type Closest = { closest(selector: string): unknown } | null;

/** What a click/keypress on `target` means for a waiting greeting. */
export function classifyGesture(target: Closest): GestureKind {
  if (!target || typeof target.closest !== "function") return "play";
  if (target.closest("[data-greeting-skip]")) return "cancel";
  if (target.closest("a[href], [data-greeting-ignore]")) return "ignore";
  return "play";
}

/** Keys that are not a deliberate gesture (modifiers alone, Escape). */
export function ignoredKey(key: string): boolean {
  return ["Shift", "Control", "Alt", "Meta", "CapsLock", "Escape", "Tab"].includes(key);
}

export const GREETING_PLAYED_KEY = "greeting-played";

export function greetingUrl(language: "en" | "ar"): string {
  return `/audio/greeting-${language}.mp3`;
}

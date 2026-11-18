// Pure motion helpers for the robot avatar (no three.js, no DOM), unit-tested in `tests/`.

const DEG = Math.PI / 180;

/** Head limits: yaw ±25°, pitch ±15° (radians). */
export const MAX_YAW = 25 * DEG;
export const MAX_PITCH = 15 * DEG;

/** No pointer movement for this long: the head starts looking around on its own. */
export const POINTER_IDLE_MS = 5000;
/** After a tap, the head looks at the touch point for this long, then looks around again. */
export const TOUCH_HOLD_MS = 2500;
/** When a card opens, the head turns toward it for this long, then follows the pointer again. */
export const CARD_FOCUS_MS = 3000;

export type Look = { yaw: number; pitch: number };
/** Where the open card is, as seen on screen: side panel (left/right) or bottom sheet (down). */
export type CardSide = "left" | "right" | "down";

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/** Frame-rate independent exponential smoothing toward `target` (`rate` per second). */
export function damp(current: number, target: number, rate: number, dt: number): number {
  return current + (target - current) * (1 - Math.exp(-rate * dt));
}

/**
 * Head angles that look at a point on the page. `center` is the avatar's center; the offset is
 * normalized by half the viewport, so the full head range covers the whole page. Positive yaw
 * turns the face to the visitor's right, positive pitch tilts it down (three.js rotation order).
 */
export function lookAt(
  point: { x: number; y: number },
  center: { x: number; y: number },
  viewport: { width: number; height: number },
): Look {
  const dx = (point.x - center.x) / Math.max(1, viewport.width / 2);
  const dy = (point.y - center.y) / Math.max(1, viewport.height / 2);
  return { yaw: clamp(dx, -1, 1) * MAX_YAW, pitch: clamp(dy, -1, 1) * MAX_PITCH };
}

/** The pose that faces the open card. */
export function cardLook(side: CardSide): Look {
  if (side === "down") return { yaw: 0, pitch: MAX_PITCH * 0.8 };
  return { yaw: (side === "right" ? 1 : -1) * MAX_YAW * 0.8, pitch: MAX_PITCH * 0.15 };
}

/** Which screen side a card opens on: the end side on desktop (RTL: left), the bottom on mobile. */
export function cardSideFor(desktop: boolean, rtl: boolean): CardSide {
  if (!desktop) return "down";
  return rtl ? "left" : "right";
}

/** Slow, aimless looking around (incommensurate sines, so it never visibly repeats). */
export function wander(t: number, bias: CardSide | null = null): Look {
  const yaw = (Math.sin(t * 0.23) * 0.55 + Math.sin(t * 0.097 + 1.3) * 0.25) * MAX_YAW;
  const pitch = (Math.sin(t * 0.17 + 0.4) * 0.35 + Math.sin(t * 0.061) * 0.15) * MAX_PITCH;
  if (!bias) return { yaw, pitch };
  // With a card open, drift around the card instead of the whole page.
  const toward = cardLook(bias);
  return { yaw: toward.yaw * 0.6 + yaw * 0.4, pitch: toward.pitch * 0.6 + pitch * 0.4 };
}

export type LookInput = {
  now: number;
  t: number;
  /** Last pointer position, its time and kind (null: no pointer seen yet). */
  pointer: { x: number; y: number; at: number; touch: boolean } | null;
  center: { x: number; y: number };
  viewport: { width: number; height: number };
  /** Side of the open card, or null. */
  card: CardSide | null;
  /** The head faces the card until this time (set when a card opens). */
  cardFocusUntil: number;
};

export type LookMode = "card" | "pointer" | "touch" | "wander";

/** Decides where the head looks this frame. */
export function chooseLook(input: LookInput): { mode: LookMode; look: Look } {
  const { now, t, pointer, card } = input;
  if (card && now < input.cardFocusUntil) return { mode: "card", look: cardLook(card) };
  if (pointer) {
    const age = now - pointer.at;
    if (pointer.touch ? age < TOUCH_HOLD_MS : age < POINTER_IDLE_MS) {
      return { mode: pointer.touch ? "touch" : "pointer", look: lookAt(pointer, input.center, input.viewport) };
    }
  }
  return { mode: "wander", look: wander(t, card) };
}

/** Time until the next blink: 3–6 s. `random` is injectable for tests. */
export function nextBlinkDelay(random: () => number = Math.random): number {
  return 3000 + random() * 3000;
}

const BLINK_CLOSE_MS = 70;
const BLINK_OPEN_MS = 110;

/** How closed the eyes are (0 open … 1 shut), `elapsed` ms after a blink started. */
export function blinkAmount(elapsed: number): number {
  if (elapsed < 0 || elapsed >= BLINK_CLOSE_MS + BLINK_OPEN_MS) return 0;
  if (elapsed < BLINK_CLOSE_MS) return elapsed / BLINK_CLOSE_MS;
  return 1 - (elapsed - BLINK_CLOSE_MS) / BLINK_OPEN_MS;
}

/**
 * A speech-like rhythm for when no audio can be measured (browser voice, text-only replies):
 * syllable pulses around 4–5 Hz with phrase-level swells, louder in the middle bars.
 */
export function syntheticLevels(t: number, count: number): number[] {
  const syllable = Math.max(0, Math.sin(t * 2 * Math.PI * 4.3)) ** 0.6;
  const phrase = 0.55 + 0.45 * Math.sin(t * 1.7 + Math.sin(t * 0.6) * 2);
  const envelope = syllable * phrase;
  const out: number[] = [];
  const mid = (count - 1) / 2;
  for (let i = 0; i < count; i++) {
    const shape = 1 - (Math.abs(i - mid) / (mid + 1)) * 0.6;
    const jitter = 0.75 + 0.25 * Math.sin(t * 13.1 + i * 2.4);
    out.push(clamp(envelope * shape * jitter, 0, 1));
  }
  return out;
}

/** Mean of a level array (0 for empty). */
export function average(values: readonly number[]): number {
  if (values.length === 0) return 0;
  let sum = 0;
  for (const value of values) sum += value;
  return sum / values.length;
}

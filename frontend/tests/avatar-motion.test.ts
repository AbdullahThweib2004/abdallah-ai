import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  CARD_FOCUS_MS,
  MAX_PITCH,
  MAX_YAW,
  POINTER_IDLE_MS,
  TOUCH_HOLD_MS,
  blinkAmount,
  cardSideFor,
  chooseLook,
  damp,
  lookAt,
  nextBlinkDelay,
  syntheticLevels,
  wander,
  type LookInput,
} from "../lib/avatar/motion.ts";

const center = { x: 500, y: 400 };
const viewport = { width: 1000, height: 800 };

function input(overrides: Partial<LookInput>): LookInput {
  return { now: 10_000, t: 10, pointer: null, center, viewport, card: null, cardFocusUntil: 0, ...overrides };
}

describe("lookAt", () => {
  it("turns right/down toward a pointer at the bottom right, clamped to the limits", () => {
    const look = lookAt({ x: 5000, y: 5000 }, center, viewport);
    assert.equal(look.yaw, MAX_YAW);
    assert.equal(look.pitch, MAX_PITCH);
  });
  it("turns left/up toward the top left and faces forward at the center", () => {
    const look = lookAt({ x: 250, y: 200 }, center, viewport);
    assert.ok(look.yaw < 0 && look.pitch < 0);
    assert.deepEqual(lookAt(center, center, viewport), { yaw: 0, pitch: 0 });
  });
});

describe("chooseLook", () => {
  it("follows a mouse until it has been still for 5 s, then looks around", () => {
    const pointer = { x: 900, y: 400, at: 10_000, touch: false };
    assert.equal(chooseLook(input({ pointer, now: 10_000 + POINTER_IDLE_MS - 1 })).mode, "pointer");
    assert.equal(chooseLook(input({ pointer, now: 10_000 + POINTER_IDLE_MS })).mode, "wander");
  });
  it("looks at a touch point briefly, then returns to looking around", () => {
    const pointer = { x: 100, y: 700, at: 10_000, touch: true };
    const held = chooseLook(input({ pointer, now: 10_000 + TOUCH_HOLD_MS - 1 }));
    assert.equal(held.mode, "touch");
    assert.ok(held.look.yaw < 0 && held.look.pitch > 0);
    assert.equal(chooseLook(input({ pointer, now: 10_000 + TOUCH_HOLD_MS })).mode, "wander");
  });
  it("faces a newly opened card first (RTL: the left side), then the pointer again", () => {
    const pointer = { x: 900, y: 400, at: 10_000, touch: false };
    const card = cardSideFor(true, true);
    assert.equal(card, "left");
    const focused = chooseLook(input({ pointer, card, cardFocusUntil: 10_000 + CARD_FOCUS_MS }));
    assert.equal(focused.mode, "card");
    assert.ok(focused.look.yaw < 0);
    const after = chooseLook(input({ pointer, card, now: 10_500, cardFocusUntil: 10_400 }));
    assert.equal(after.mode, "pointer");
  });
  it("puts the card on the right in LTR and below on mobile", () => {
    assert.equal(cardSideFor(true, false), "right");
    assert.equal(cardSideFor(false, true), "down");
  });
});

describe("motion helpers", () => {
  it("damp converges toward the target independently of frame rate", () => {
    let fast = 0;
    for (let i = 0; i < 60; i++) fast = damp(fast, 1, 5, 1 / 60);
    let slow = 0;
    for (let i = 0; i < 30; i++) slow = damp(slow, 1, 5, 1 / 30);
    assert.ok(Math.abs(fast - slow) < 1e-9);
    assert.ok(fast > 0.99);
  });
  it("wander stays inside the head limits", () => {
    for (let t = 0; t < 600; t += 0.37) {
      const look = wander(t, t > 300 ? "right" : null);
      assert.ok(Math.abs(look.yaw) <= MAX_YAW && Math.abs(look.pitch) <= MAX_PITCH);
    }
  });
  it("blinks every 3–6 s and a blink closes then reopens", () => {
    assert.equal(nextBlinkDelay(() => 0), 3000);
    assert.equal(nextBlinkDelay(() => 0.999999) < 6000, true);
    assert.equal(blinkAmount(0), 0);
    assert.equal(blinkAmount(70), 1);
    assert.ok(blinkAmount(120) > 0 && blinkAmount(120) < 1);
    assert.equal(blinkAmount(500), 0);
  });
  it("synthetic speech levels stay in 0..1 and are not flat", () => {
    const seen = new Set<number>();
    for (let t = 0; t < 3; t += 0.05) {
      const bars = syntheticLevels(t, 7);
      assert.equal(bars.length, 7);
      for (const bar of bars) assert.ok(bar >= 0 && bar <= 1);
      seen.add(Math.round(bars[3] * 10));
    }
    assert.ok(seen.size > 4);
  });
});

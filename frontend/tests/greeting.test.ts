import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  type GreetingEvent,
  type GreetingState,
  classifyGesture,
  greetingReducer,
  greetingUrl,
  ignoredKey,
  initialGreeting,
} from "../lib/voice/greeting.ts";

const run = (events: GreetingEvent[], from: GreetingState = initialGreeting) => events.reduce(greetingReducer, from);
const load = { type: "load", muted: false, playedThisVisit: false, conversationStarted: false } as const;

describe("greeting autoplay and first gesture", () => {
  it("plays at once when autoplay is allowed, then is done", () => {
    const playing = run([load, { type: "result", result: "playing" }]);
    assert.equal(playing.phase, "playing");
    assert.equal(run([{ type: "ended" }], playing).phase, "done");
  });

  it("waits when blocked and plays on the first ordinary gesture", () => {
    const waiting = run([load, { type: "result", result: "blocked" }]);
    assert.equal(waiting.phase, "waiting");
    const trying = run([{ type: "gesture", kind: "play" }], waiting);
    assert.deepEqual(trying, { phase: "trying", viaGesture: true });
    assert.equal(run([{ type: "result", result: "playing" }], trying).phase, "playing");
  });

  it("a gesture that starts its own flow cancels it; links and the language switch are ignored", () => {
    const waiting = run([load, { type: "result", result: "blocked" }]);
    assert.equal(run([{ type: "gesture", kind: "cancel" }], waiting).phase, "done");
    assert.equal(run([{ type: "gesture", kind: "ignore" }], waiting).phase, "waiting");
  });

  it("never plays when muted, already played this visit, or a conversation started", () => {
    for (const flags of [
      { muted: true, playedThisVisit: false, conversationStarted: false },
      { muted: false, playedThisVisit: true, conversationStarted: false },
      { muted: false, playedThisVisit: false, conversationStarted: true },
    ]) {
      assert.equal(run([{ ...load, ...flags }]).phase, "done");
    }
    const waiting = run([load, { type: "result", result: "blocked" }]);
    assert.equal(run([{ type: "mute" }], waiting).phase, "done");
    assert.equal(run([{ type: "mute" }], run([{ type: "result", result: "playing" }], run([load]))).phase, "done");
  });

  it("plays once: after it ended (or was cancelled) no event starts it again", () => {
    const finished = run([load, { type: "result", result: "playing" }, { type: "ended" }]);
    for (const event of [load, { type: "gesture", kind: "play" }, { type: "result", result: "playing" }] as GreetingEvent[]) {
      assert.equal(greetingReducer(finished, event), finished);
    }
  });

  it("a file that fails on load waits for a gesture (fallback voice); failing in a gesture gives up", () => {
    const waiting = run([load, { type: "result", result: "failed" }]);
    assert.equal(waiting.phase, "waiting");
    assert.equal(run([{ type: "gesture", kind: "play" }, { type: "result", result: "failed" }], waiting).phase, "done");
  });

  it("gestures while not waiting change nothing", () => {
    const trying = run([load]);
    assert.equal(run([{ type: "gesture", kind: "play" }], trying), trying);
  });
});

describe("gesture classification", () => {
  const target = (matches: string[]) => ({
    closest: (selector: string) => (selector.split(",").some((part) => matches.includes(part.trim())) ? {} : null),
  });

  it("composer and chips cancel, links and the language switcher are ignored, the rest plays", () => {
    assert.equal(classifyGesture(target(["[data-greeting-skip]"])), "cancel");
    assert.equal(classifyGesture(target(["a[href]"])), "ignore");
    assert.equal(classifyGesture(target(["[data-greeting-ignore]"])), "ignore");
    assert.equal(classifyGesture(target([])), "play");
    assert.equal(classifyGesture(null), "play");
  });

  it("modifier keys, Tab and Escape are not gestures", () => {
    assert.equal(ignoredKey("Shift"), true);
    assert.equal(ignoredKey("Tab"), true);
    assert.equal(ignoredKey(" "), false);
    assert.equal(ignoredKey("a"), false);
  });

  it("uses the language at play time", () => {
    assert.equal(greetingUrl("en"), "/audio/greeting-en.mp3");
    assert.equal(greetingUrl("ar"), "/audio/greeting-ar.mp3");
  });
});

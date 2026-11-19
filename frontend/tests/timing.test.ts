import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  type Alignment,
  offsetTokens,
  progressAt,
  proportionalTimes,
  sourceIndex,
  timeTokens,
  tokenize,
} from "../lib/voice/timing.ts";
import { entryView, wordState } from "../lib/voice/transcript.ts";

/** A fake alignment: each character of `spoken` lasts `step` seconds. */
function align(spoken: string, step = 0.05, from = 0): Alignment {
  const chars = [...spoken];
  return {
    chars,
    starts: chars.map((_, i) => from + i * step),
    ends: chars.map((_, i) => from + (i + 1) * step),
  };
}

const words = (timed: { text: string; t0: number; t1: number }[]) => timed.map((t) => [t.text, +t.t0.toFixed(2), +t.t1.toFixed(2)]);

describe("character alignment → word timing", () => {
  it("English: punctuation stays with its word", () => {
    const text = "Hi, I'm Abdallah.";
    const timed = timeTokens(tokenize(text), align(text, 0.1));
    assert.deepEqual(words(timed), [
      ["Hi,", 0, 0.2],
      ["I'm", 0.4, 0.7],
      ["Abdallah.", 0.8, 1.6],
    ]);
  });

  it("Arabic, with diacritics and alef forms normalized", () => {
    const display = "أهلاً بك في موقعه";
    const timed = timeTokens(tokenize(display), align("اهلا بك في موقعه", 0.1));
    assert.equal(timed.length, 4);
    assert.ok(timed.every((t, i) => i === 0 || t.t0 >= timed[i - 1].t1 - 1e-9), "monotonic");
    assert.equal(timed[3].text, "موقعه");
    assert.ok(Math.abs(timed[3].t1 - 1.6) < 1e-9);
  });

  it("mixed Arabic + English, and the server's inserted space (وReact → و React)", () => {
    const display = "استخدم وReact و FastAPI";
    const timed = timeTokens(tokenize(display), align("استخدم و React و FastAPI", 0.05));
    assert.deepEqual(timed.map((t) => t.text), ["استخدم", "وReact", "و", "FastAPI"]);
    const react = timed[1];
    assert.ok(react.t0 < react.t1 && react.t1 <= timed[3].t0 + 1e-9);
  });

  it("numbers like 97.15 are one word", () => {
    const text = "accuracy 97.15% on MNIST";
    const timed = timeTokens(tokenize(text), align(text, 0.05));
    assert.deepEqual(timed.map((t) => t.text), ["accuracy", "97.15%", "on", "MNIST"]);
    assert.ok(timed[1].t1 > timed[1].t0);
  });

  it("words the server replaced are interpolated between their neighbours", () => {
    const display = "Email abdullah@example.com today.";
    const timed = timeTokens(tokenize(display), align("Email his email today.", 0.1));
    assert.equal(timed.length, 3);
    assert.ok(timed[1].t0 >= timed[0].t1 - 1e-9 && timed[1].t1 <= timed[2].t0 + 1e-9);
  });

  it("proportional fallback without any alignment", () => {
    const timed = proportionalTimes(tokenize("one three"), 2);
    assert.deepEqual(words(timed), [
      ["one", 0, 0.8],
      ["three", 0.8, 2],
    ]);
  });
});

describe("progress over several sentence chunks", () => {
  const answer = "First part. Second one.";
  const sentences = [
    { text: "First part.", offset: 0 },
    { text: "Second one.", offset: 12 },
  ];
  // Each sentence is its own audio clip: times restart at 0 for each.
  const items = sentences.map((s) => offsetTokens(timeTokens(tokenize(s.text), align(s.text, 0.1)), s.offset));

  it("offsets map sentence words onto the answer text", () => {
    assert.equal(answer.slice(items[1][0].start, items[1][0].end), "Second");
  });

  it("lights words as they start; the current word glows; pauses have no current word", () => {
    assert.deepEqual(progressAt(items[0], 0.05), { litUpTo: 5, current: items[0][0] });
    assert.equal(progressAt(items[0], 0.55).current, null); // the space before "part."
    assert.equal(progressAt(items[0], 0.65).litUpTo, 11);
    assert.equal(progressAt(items[1], 0.01).litUpTo, 18); // second clip: answer offsets
  });

  it("maps a browser-voice boundary index back to the source text", () => {
    assert.equal(sourceIndex("وReact", "و React", 2), 1); // the inserted space is skipped
    assert.equal(sourceIndex("abc", "abc", 2), 2);
  });
});

describe("entry views", () => {
  it("muted or unvoiced answers are fully bright", () => {
    const view = entryView(undefined, null);
    assert.equal(wordState(view, 0, 5), "spoken");
  });

  it("live: lit, current and pending words; text that arrived before its audio is dimmed", () => {
    const view = entryView({ state: "live" }, { litUpTo: 10, current: { start: 6, end: 10 } });
    assert.equal(wordState(view, 0, 5), "spoken");
    assert.equal(wordState(view, 6, 10), "current");
    assert.equal(wordState(view, 11, 15), "pending");
    assert.equal(wordState(entryView({ state: "live" }, null), 0, 5), "pending");
  });

  it("stopped: spoken words stay bright, the rest stays dimmed, no glow", () => {
    const view = entryView({ state: "stopped", litUpTo: 10 }, { litUpTo: 99, current: { start: 11, end: 15 } });
    assert.equal(view.mode === "lit" && view.stopped, true);
    assert.equal(wordState(view, 6, 10), "spoken");
    assert.equal(wordState(view, 11, 15), "pending");
  });

  it("done and pending", () => {
    assert.equal(wordState(entryView({ state: "done" }, null), 50, 60), "spoken");
    assert.equal(wordState(entryView({ state: "pending" }, null), 0, 5), "pending");
  });
});

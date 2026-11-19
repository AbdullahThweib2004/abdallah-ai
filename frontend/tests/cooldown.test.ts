import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { busyMessage, cooldownUntil, secondsLeft } from "../lib/conversation/cooldown.ts";

const EN = {
  one: "Busy right now, try again in 1 second.",
  two: "Busy right now, try again in {n} seconds.",
  few: "Busy right now, try again in {n} seconds.",
  many: "Busy right now, try again in {n} seconds.",
  other: "Busy right now, try again in {n} seconds.",
};
const AR = {
  one: "مشغول الآن، حاول مرة أخرى بعد ثانية واحدة.",
  two: "مشغول الآن، حاول مرة أخرى بعد ثانيتين.",
  few: "مشغول الآن، حاول مرة أخرى بعد {n} ثوانٍ.",
  many: "مشغول الآن، حاول مرة أخرى بعد {n} ثانية.",
  other: "مشغول الآن، حاول مرة أخرى بعد {n} ثانية.",
};

describe("countdown", () => {
  it("counts whole seconds down to zero and never below", () => {
    const until = cooldownUntil(8, 1_000_000);
    assert.equal(secondsLeft(until, 1_000_000), 8);
    assert.equal(secondsLeft(until, 1_000_000 + 7_200), 1); // 0.8 s left still shows 1
    assert.equal(secondsLeft(until, 1_000_000 + 8_000), 0); // composer re-enables
    assert.equal(secondsLeft(until, 1_000_000 + 60_000), 0);
  });
  it("falls back to 20 s for a missing or invalid Retry-After and caps at an hour", () => {
    assert.equal(cooldownUntil(Number.NaN, 0), 20_000);
    assert.equal(cooldownUntil(0, 0), 20_000);
    assert.equal(cooldownUntil(99_999, 0), 3_600_000);
  });
});

describe("busyMessage", () => {
  it("uses English singular and plural", () => {
    assert.equal(busyMessage(EN, "en", 1), "Busy right now, try again in 1 second.");
    assert.equal(busyMessage(EN, "en", 12), "Busy right now, try again in 12 seconds.");
  });
  it("uses the Arabic one/two/few/many forms", () => {
    assert.equal(busyMessage(AR, "ar", 1), AR.one);
    assert.equal(busyMessage(AR, "ar", 2), AR.two);
    assert.equal(busyMessage(AR, "ar", 5), "مشغول الآن، حاول مرة أخرى بعد 5 ثوانٍ.");
    assert.equal(busyMessage(AR, "ar", 15), "مشغول الآن، حاول مرة أخرى بعد 15 ثانية.");
  });
});

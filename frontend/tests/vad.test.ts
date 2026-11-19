import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { CALIBRATION_MS, MIN_SPEECH_RMS, VoiceActivity, estimateNoiseFloor } from "../lib/voice/vad.ts";

/** Feed `levels` at 50 ms ticks starting at t=0; returns the detector. */
function run(levels: number[]): VoiceActivity {
  const vad = new VoiceActivity(0);
  levels.forEach((rms, index) => vad.update(rms, index * 50));
  return vad;
}

const speech = (ticks: number, loud = 0.1, gap = 0.004) =>
  Array.from({ length: ticks }, (_, index) => (index % 4 === 3 ? gap : loud)); // syllable gaps
const silence = (ticks: number, level = 0.003) => Array.from({ length: ticks }, () => level);

describe("voice activity detection", () => {
  it("keeps speech that starts at 0 ms, during calibration", () => {
    const vad = run([...speech(30), ...silence(10)]);
    assert.equal(vad.heardSpeech, true);
    assert.equal(vad.lastVoiceAt, 29 * 50); // last loud tick of the speech
    assert.ok(vad.threshold() < 0.1 / 2, "speech did not become the noise floor");
  });

  it("the old max-based calibration would have missed it (regression guard)", () => {
    const first300 = speech(CALIBRATION_MS / 50 + 1);
    const oldThreshold = Math.max(MIN_SPEECH_RMS, Math.max(...first300) * 3);
    assert.ok(oldThreshold > 0.1); // nothing in this speech would ever count as voice
  });

  it("still detects speech after a quiet start", () => {
    const vad = run([...silence(10), ...speech(20)]);
    assert.equal(vad.heardSpeech, true);
  });

  it("adapts to a noisy room after calibration: noise is not speech, speech is", () => {
    const noisy = silence(12, 0.03);
    const quietOnly = run(noisy);
    assert.equal(quietOnly.heardSpeech, false, "steady 0.03 noise is background");
    assert.ok(quietOnly.threshold() > 0.03);
    const withSpeech = run([...noisy, ...speech(20, 0.2, 0.03)]);
    assert.equal(withSpeech.heardSpeech, true);
  });

  it("uses the fixed default threshold (provisionally) until calibration finishes", () => {
    const vad = new VoiceActivity(0);
    assert.equal(vad.update(0.05, 0), true);
    assert.equal(vad.update(0.05, 50), true);
    assert.equal(vad.calibrated, false);
    assert.equal(vad.heardSpeech, false, "nothing is latched during calibration");
    assert.equal(vad.threshold(), MIN_SPEECH_RMS);
    for (let t = 100; t <= CALIBRATION_MS; t += 50) vad.update(t === 200 ? 0.002 : 0.05, t);
    assert.equal(vad.calibrated, true);
    assert.equal(vad.heardSpeech, true, "the calibration window's speech counts once replayed");
  });

  it("estimates noise from the quietest sample", () => {
    assert.equal(estimateNoiseFloor([0.1, 0.1, 0.002, 0.1, 0.004, 0.1]), 0.002);
    assert.equal(estimateNoiseFloor([]), 0);
  });
});

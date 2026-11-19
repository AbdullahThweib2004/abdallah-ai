/**
 * Voice-activity detection for one recording: RMS level per tick → speech / silence.
 *
 * The background level is learned during the first CALIBRATION_MS after the mic opens. Speech
 * in that window must not be lost (a visitor may start talking at once), so:
 * - until calibration ends, a fixed default threshold (MIN_SPEECH_RMS) marks ticks as voice,
 *   provisionally: nothing is latched yet;
 * - the noise floor is the QUIETEST calibration sample (a gap between sounds), so speech from
 *   0 ms does not inflate it the way a maximum would;
 * - when calibration ends, the threshold adapts to max(MIN_SPEECH_RMS, floor × NOISE_FACTOR)
 *   and the calibration samples are replayed against it: speech in that window counts, while
 *   steady background noise (louder than the default threshold in a noisy room) does not.
 */

export const CALIBRATION_MS = 300;
/** Absolute floor, also the provisional threshold during calibration. */
export const MIN_SPEECH_RMS = 0.012;
export const NOISE_FACTOR = 3;
/** Consecutive voiced ticks (~100 ms) before speech counts as started (ignores clicks). */
export const SPEECH_START_TICKS = 2;

/** The quietest sample: the background between sounds (0 when there are no samples). */
export function estimateNoiseFloor(samples: readonly number[]): number {
  return samples.length ? Math.min(...samples) : 0;
}

export class VoiceActivity {
  heardSpeech = false;
  /** Time of the last voiced tick (the end of speech once the visitor stops). */
  lastVoiceAt = 0;
  private noiseFloor: number | null = null;
  private readonly samples: { rms: number; at: number }[] = [];
  private voicedTicks = 0;
  private readonly startedAt: number;

  constructor(startedAt: number) {
    this.startedAt = startedAt;
  }

  get calibrated(): boolean {
    return this.noiseFloor !== null;
  }

  threshold(): number {
    return this.noiseFloor === null ? MIN_SPEECH_RMS : Math.max(MIN_SPEECH_RMS, this.noiseFloor * NOISE_FACTOR);
  }

  /** Feed one level reading; returns whether this tick counts as voice (so far). */
  update(rms: number, now: number): boolean {
    if (this.noiseFloor !== null) return this.count(rms, now);
    this.samples.push({ rms, at: now });
    if (now - this.startedAt < CALIBRATION_MS) return rms > MIN_SPEECH_RMS; // provisional
    this.noiseFloor = estimateNoiseFloor(this.samples.map((sample) => sample.rms));
    let voiced = false;
    for (const sample of this.samples) voiced = this.count(sample.rms, sample.at);
    return voiced;
  }

  private count(rms: number, now: number): boolean {
    const voiced = rms > this.threshold();
    if (voiced) {
      this.voicedTicks++;
      this.lastVoiceAt = now;
      if (this.voicedTicks >= SPEECH_START_TICKS) this.heardSpeech = true;
    } else {
      this.voicedTicks = 0;
    }
    return voiced;
  }
}

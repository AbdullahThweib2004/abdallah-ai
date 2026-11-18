import { LevelMeter } from "./levels";

/**
 * Records one spoken question from the microphone.
 *
 * The microphone is only opened by `Recorder.open()`, which the UI calls from a click. Simple
 * RMS voice-activity detection stops the recording after SILENCE_MS of quiet once speech was
 * heard; it also stops at MAX_MS. The clip stays in memory and is only uploaded for
 * transcription; it is never stored.
 */

export const MAX_MS = 30_000;
export const COUNTDOWN_FROM_MS = 5_000;
// Quiet time that ends a question (NEXT_PUBLIC_VAD_SILENCE_MS, default 1500, kept in 500–5000).
const SILENCE_MS = silenceMs(process.env.NEXT_PUBLIC_VAD_SILENCE_MS);
// Give up early if the visitor never starts talking.
const NO_SPEECH_TIMEOUT_MS = 8_000;
const TICK_MS = 50;
// Absolute floor and multiple of the measured background noise that count as voice.
const MIN_SPEECH_RMS = 0.012;
const NOISE_FACTOR = 3;
// Consecutive voiced ticks (~100 ms) before speech counts as started (ignores clicks).
const SPEECH_START_TICKS = 2;

const MIME_TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"];

export function silenceMs(value: string | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && value?.trim() ? Math.min(5_000, Math.max(500, parsed)) : 1_500;
}

export type MicErrorKind = "denied" | "missing" | "unsupported" | "failed";

export class MicError extends Error {
  constructor(public readonly kind: MicErrorKind) {
    super(`Microphone ${kind}`);
    this.name = "MicError";
  }
}

export type Recording = {
  blob: Blob;
  /** False when no speech was detected at all (nothing worth uploading). */
  heardSpeech: boolean;
  durationMs: number;
};

type Callbacks = {
  /** Remaining milliseconds during the last COUNTDOWN_FROM_MS, else null. */
  onCountdown: (remainingMs: number | null) => void;
  onStop: (recording: Recording) => void;
};

export class Recorder {
  private readonly chunks: Blob[] = [];
  private readonly meter: LevelMeter;
  private timer: ReturnType<typeof setInterval> | null = null;
  private startedAt = 0;
  private noiseFloor = 0;
  private voicedTicks = 0;
  private heardSpeech = false;
  private lastVoiceAt = 0;
  private stopped = false;
  private cancelled = false;

  private constructor(
    private readonly stream: MediaStream,
    private readonly context: AudioContext,
    private readonly recorder: MediaRecorder,
    private readonly callbacks: Callbacks,
  ) {
    const analyser = context.createAnalyser();
    context.createMediaStreamSource(stream).connect(analyser);
    this.meter = new LevelMeter(analyser);
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    });
    recorder.addEventListener("stop", () => this.finish());
  }

  static supported(): boolean {
    return (
      typeof navigator !== "undefined" &&
      !!navigator.mediaDevices?.getUserMedia &&
      typeof MediaRecorder !== "undefined" &&
      typeof AudioContext !== "undefined"
    );
  }

  /** Ask for the microphone (permission prompt) and start recording. */
  static async open(callbacks: Callbacks): Promise<Recorder> {
    if (!Recorder.supported()) throw new MicError("unsupported");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch (error) {
      const name = error instanceof DOMException ? error.name : "";
      if (name === "NotAllowedError" || name === "SecurityError") throw new MicError("denied");
      if (name === "NotFoundError" || name === "OverconstrainedError" || name === "NotReadableError") {
        throw new MicError("missing");
      }
      throw new MicError("failed");
    }
    const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
    try {
      const recorder = new MediaRecorder(stream, { mimeType, audioBitsPerSecond: 32_000 });
      const instance = new Recorder(stream, new AudioContext(), recorder, callbacks);
      instance.start();
      return instance;
    } catch {
      stream.getTracks().forEach((track) => track.stop());
      throw new MicError("failed");
    }
  }

  /** Per-bar input levels for the avatar. */
  levels(): number[] {
    return this.meter.bars();
  }

  /** Stop and deliver the clip (click on the mic again). */
  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    if (this.timer) clearInterval(this.timer);
    if (this.recorder.state !== "inactive") this.recorder.stop();
    else this.finish();
  }

  /** Stop and throw the clip away (page leaves, Stop button). */
  cancel(): void {
    this.cancelled = true;
    this.stop();
  }

  private start(): void {
    void this.context.resume();
    this.startedAt = performance.now();
    this.recorder.start(250);
    this.timer = setInterval(() => this.tick(), TICK_MS);
  }

  private tick(): void {
    const now = performance.now();
    const elapsed = now - this.startedAt;
    const rms = this.meter.rms();

    // Learn the background level during the first 300 ms (before anyone talks).
    if (elapsed < 300) this.noiseFloor = Math.max(this.noiseFloor, rms);
    const threshold = Math.max(MIN_SPEECH_RMS, this.noiseFloor * NOISE_FACTOR);
    if (rms > threshold) {
      this.voicedTicks++;
      this.lastVoiceAt = now;
      if (this.voicedTicks >= SPEECH_START_TICKS) this.heardSpeech = true;
    } else {
      this.voicedTicks = 0;
    }

    const remaining = MAX_MS - elapsed;
    this.callbacks.onCountdown(remaining <= COUNTDOWN_FROM_MS ? Math.max(0, remaining) : null);

    if (remaining <= 0) return this.stop();
    if (this.heardSpeech && now - this.lastVoiceAt >= SILENCE_MS) return this.stop();
    if (!this.heardSpeech && elapsed >= NO_SPEECH_TIMEOUT_MS) return this.stop();
  }

  private finish(): void {
    if (this.timer) clearInterval(this.timer);
    this.stream.getTracks().forEach((track) => track.stop()); // mic indicator off
    void this.context.close();
    this.callbacks.onCountdown(null);
    if (this.cancelled) return;
    if (this.heardSpeech) {
      // The moment the visitor stopped talking (for the end-of-speech → first-audio metric).
      performance.mark("voice:speech-end", { startTime: this.lastVoiceAt });
    }
    this.callbacks.onStop({
      blob: new Blob(this.chunks, { type: this.recorder.mimeType || "audio/webm" }),
      heardSpeech: this.heardSpeech,
      durationMs: performance.now() - this.startedAt,
    });
  }
}

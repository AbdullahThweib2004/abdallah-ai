import { VoiceHttpError, fetchSpeech } from "@/services/voice";
import type { ChatLanguage } from "@/services/types";

import { spaceArabicLatin } from "@/lib/text/spacing";
import { LevelMeter } from "./levels";
import { SentenceSplitter } from "./sentences";

/**
 * Speaks a streamed answer sentence by sentence.
 *
 * Each sentence is sent to `/voice/speak` as soon as the splitter completes it (at most
 * MAX_IN_FLIGHT at a time) and played in order from a queue, so the first audio starts long
 * before the answer has finished streaming. The first sentence is played while it is still
 * downloading (MediaSource), later ones are usually complete by their turn.
 *
 * If the server voice fails or its budget is used up, the rest of THAT answer is spoken by
 * the browser's own speechSynthesis, silently for the visitor (console only). After a
 * `tts_quota` the server voice stays off for this page visit.
 *
 * One <audio> element is routed through an AnalyserNode once, so the avatar's waveform
 * follows the real audio level.
 */

const MAX_IN_FLIGHT = 2;
const MSE_TYPE = "audio/mpeg";

export type VoiceMode = "server" | "browser";

export type SpeakerState = {
  /** Audio is audible right now. */
  speaking: boolean;
  /** An answer is being voiced (queued, loading or playing). */
  active: boolean;
};

type Item = {
  text: string;
  language: ChatLanguage;
  chunks: Uint8Array<ArrayBuffer>[];
  done: boolean;
  failed: boolean;
  started: boolean;
  listeners: Set<() => void>;
  /** A static clip (the greeting), not part of an answer: never marks the composer busy. */
  clip?: boolean;
};

type Answer = {
  language: ChatLanguage;
  mode: VoiceMode;
  splitter: SentenceSplitter;
  abort: AbortController;
  ended: boolean;
  firstAudio: boolean;
};

type Callbacks = {
  onState: (state: SpeakerState) => void;
  /** No speechSynthesis voice for this language on this device: captions only. */
  onBrowserVoiceMissing: (language: ChatLanguage) => void;
};

function notify(item: Item) {
  for (const listener of item.listeners) listener();
}

function bcp47(language: ChatLanguage): string {
  return language === "ar" ? "ar-SA" : "en-US";
}

export class Speaker {
  private context: AudioContext | null = null;
  private meter: LevelMeter | null = null;
  private readonly audio: HTMLAudioElement | null;
  private answer: Answer | null = null;
  private queue: Item[] = [];
  private current: Item | null = null;
  private inFlight = 0;
  private pendingFetches: Item[] = [];
  private objectUrl: string | null = null;
  private serverVoice: boolean;
  private speaking = false;
  private browserVoice = false;
  private clipEnded: (() => void) | null = null;
  private clipToken = 0;

  constructor(
    mode: VoiceMode,
    private readonly callbacks: Callbacks,
  ) {
    this.serverVoice = mode === "server";
    this.audio = typeof Audio === "undefined" ? null : new Audio();
    if (this.audio) {
      this.audio.preload = "auto";
      this.audio.addEventListener("playing", () => this.onPlaying());
      this.audio.addEventListener("ended", () => this.finishCurrent());
      this.audio.addEventListener("error", () => this.finishCurrent());
    }
  }

  /** Call inside a user gesture (click/keypress): browsers only allow audio after one. */
  unlock(): void {
    if (!this.audio || typeof AudioContext === "undefined") return;
    if (!this.context) {
      this.context = new AudioContext();
      const analyser = this.context.createAnalyser();
      this.context.createMediaElementSource(this.audio).connect(analyser);
      analyser.connect(this.context.destination);
      this.meter = new LevelMeter(analyser);
    }
    if (this.context.state === "suspended") void this.context.resume();
    // Load the voice list early; Chrome fills it asynchronously.
    if (typeof speechSynthesis !== "undefined") speechSynthesis.getVoices();
  }

  get unlocked(): boolean {
    return this.context !== null;
  }

  /** Per-bar levels of the audio playing now, or null when nothing measurable plays. */
  levels(): number[] | null {
    return this.speaking && !this.browserVoice && this.meter ? this.meter.bars() : null;
  }

  /**
   * Play a static clip (the greeting) through the same element and analyser as answers, so the
   * avatar follows its real level. `viaGesture`: called inside a user gesture (may unlock audio
   * and use the browser voice if the file fails). Without a gesture this is the autoplay
   * attempt: "blocked" when the browser refuses sound. `onEnd` runs once, when it finishes or
   * is stopped (Stop, a new answer, mute).
   */
  async playGreeting(
    url: string,
    text: string,
    language: ChatLanguage,
    viaGesture: boolean,
    onEnd: () => void,
  ): Promise<"playing" | "blocked" | "failed"> {
    const audio = this.audio;
    if (!audio) return "failed";
    this.stop();
    const token = ++this.clipToken;
    if (viaGesture) this.unlock();
    const item: Item = {
      text, language, chunks: [], done: true, failed: false, started: true, listeners: new Set(), clip: true,
    };
    this.current = item;
    this.clipEnded = onEnd;
    audio.src = url;
    try {
      await audio.play();
    } catch (error) {
      // Replaced meanwhile (Stop, a new answer). A load error may already have cleared
      // `current` through the element's error event, so compare the call, not the item.
      if (token !== this.clipToken || this.answer) return "failed";
      const blocked = error instanceof DOMException && error.name === "NotAllowedError";
      this.resetClip();
      if (blocked) return "blocked";
      if (!viaGesture) return "blocked"; // the browser-voice fallback needs a gesture too
      console.info("[voice] greeting file unavailable; using the browser voice", error);
      this.current = item;
      this.clipEnded = onEnd;
      this.speakWithBrowser(item);
      return this.current === item ? "playing" : "failed";
    }
    if (!viaGesture) {
      // Autoplay allowed: route it through the analyser for real levels. If the audio graph
      // cannot run without a gesture, the element would be silent: treat as blocked.
      this.unlock();
      if (this.context && this.context.state !== "running") {
        await Promise.race([this.context.resume(), new Promise((resolve) => setTimeout(resolve, 300))]);
      }
      if (this.context && this.context.state !== "running") {
        this.resetClip();
        return "blocked";
      }
    }
    return this.current === item ? "playing" : "failed";
  }

  /** Drop the greeting clip without calling its end callback (a retry follows). */
  private resetClip(): void {
    this.clipEnded = null;
    this.current = null;
    if (this.audio) {
      this.audio.pause();
      this.audio.removeAttribute("src");
      this.audio.load();
    }
    this.speaking = false;
    this.emit();
  }

  private endClip(): void {
    const ended = this.clipEnded;
    this.clipEnded = null;
    ended?.();
  }

  begin(language: ChatLanguage): void {
    this.stop();
    this.answer = {
      language,
      mode: this.serverVoice ? "server" : "browser",
      splitter: new SentenceSplitter(),
      abort: new AbortController(),
      ended: false,
      firstAudio: false,
    };
    this.emit();
  }

  push(text: string): void {
    if (!this.answer || this.answer.ended) return;
    for (const sentence of this.answer.splitter.push(text)) this.enqueue(sentence);
  }

  end(): void {
    if (!this.answer || this.answer.ended) return;
    for (const sentence of this.answer.splitter.flush()) this.enqueue(sentence);
    this.answer.ended = true;
    this.pump();
    this.emit();
  }

  /** Stop all speech now (Stop button, barge-in, new question). */
  stop(): void {
    this.clipToken++; // a greeting attempt in progress is cancelled too
    if (this.current?.clip) this.endClip();
    this.answer?.abort.abort();
    this.answer = null;
    this.queue = [];
    this.pendingFetches = [];
    this.inFlight = 0;
    this.current = null;
    if (this.audio) {
      this.audio.pause();
      this.audio.removeAttribute("src");
      this.audio.load();
    }
    this.revoke();
    if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
    this.speaking = false;
    this.browserVoice = false;
    this.emit();
  }

  dispose(): void {
    this.stop();
    void this.context?.close();
    this.context = null;
  }

  // ------------------------------------------------------------------------------- queue

  private enqueue(text: string): void {
    const answer = this.answer;
    if (!answer) return;
    const item: Item = {
      // "وReact" would be read as one word; both voices get "و React".
      text: spaceArabicLatin(text),
      language: answer.language,
      chunks: [],
      done: false,
      failed: false,
      started: false,
      listeners: new Set(),
    };
    this.queue.push(item);
    if (answer.mode === "server") {
      this.pendingFetches.push(item);
      this.startFetches();
    }
    this.pump();
  }

  private startFetches(): void {
    while (this.inFlight < MAX_IN_FLIGHT && this.pendingFetches.length) {
      const item = this.pendingFetches.shift()!;
      this.inFlight++;
      void this.download(item).finally(() => {
        this.inFlight = Math.max(0, this.inFlight - 1);
        this.startFetches();
      });
    }
  }

  private async download(item: Item): Promise<void> {
    const answer = this.answer;
    if (!answer) return;
    if (answer.mode === "browser") {
      item.failed = true; // an earlier sentence already fell back
      notify(item);
      return;
    }
    try {
      const response = await fetchSpeech(item.text, item.language, answer.abort.signal);
      const reader = response.body!.getReader();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        item.chunks.push(value as Uint8Array<ArrayBuffer>);
        notify(item);
      }
    } catch (error) {
      if (answer.abort.signal.aborted) return;
      if (item.chunks.length === 0) {
        // Silent fallback: this and every later sentence of the answer use the browser voice.
        const code = error instanceof VoiceHttpError ? error.code : null;
        console.info(`[voice] server voice unavailable (${code ?? "network"}); using the browser voice`);
        answer.mode = "browser";
        if (code === "tts_quota") this.serverVoice = false;
        item.failed = true;
      }
    }
    item.done = true;
    notify(item);
  }

  private pump(): void {
    if (this.current || !this.answer) return;
    const item = this.queue[0];
    if (!item) {
      if (this.answer.ended) {
        this.answer = null;
        this.speaking = false;
        this.emit();
      }
      return;
    }
    if (this.answer.mode === "browser" || item.failed) {
      this.queue.shift();
      this.current = item;
      this.speakWithBrowser(item);
      return;
    }
    if (item.chunks.length === 0 && !item.done) {
      // Wait for the first bytes (or a failure) of the next sentence.
      const retry = () => {
        item.listeners.delete(retry);
        this.pump();
      };
      item.listeners.add(retry);
      return;
    }
    this.queue.shift();
    this.current = item;
    this.playServerAudio(item);
  }

  private finishCurrent(): void {
    if (!this.current) return;
    if (this.current.clip) this.endClip();
    this.current = null;
    this.revoke();
    this.speaking = false;
    this.browserVoice = false;
    // Keep `speaking` true between sentences if more are queued, to avoid avatar flicker.
    if (this.queue.length) this.speaking = true;
    this.emit();
    this.pump();
  }

  // ------------------------------------------------------------------------- playback

  private playServerAudio(item: Item): void {
    const audio = this.audio;
    if (!audio) return this.finishCurrent();
    item.started = true;
    const streaming =
      !item.done && typeof MediaSource !== "undefined" && MediaSource.isTypeSupported(MSE_TYPE);

    if (streaming) {
      const source = new MediaSource();
      this.objectUrl = URL.createObjectURL(source);
      source.addEventListener("sourceopen", () => this.feed(source, item), { once: true });
    } else if (item.done) {
      this.objectUrl = URL.createObjectURL(new Blob(item.chunks, { type: MSE_TYPE }));
    } else {
      // No MediaSource (e.g. older Safari): wait until the sentence is fully downloaded.
      const ready = () => {
        if (!item.done) return;
        item.listeners.delete(ready);
        if (this.current === item) {
          this.current = null;
          this.queue.unshift(item);
          this.pump();
        }
      };
      item.listeners.add(ready);
      return;
    }
    audio.src = this.objectUrl;
    audio.play().catch((error: unknown) => {
      // Autoplay refused (no user gesture yet) or the clip was replaced: skip quietly.
      if (error instanceof DOMException && error.name === "AbortError") return;
      console.info("[voice] playback refused:", error);
      this.stop();
    });
  }

  private feed(source: MediaSource, item: Item): void {
    let buffer: SourceBuffer;
    try {
      buffer = source.addSourceBuffer(MSE_TYPE);
    } catch {
      return this.finishCurrent();
    }
    let appended = 0;
    const next = () => {
      if (this.current !== item || source.readyState !== "open" || buffer.updating) return;
      if (appended < item.chunks.length) {
        buffer.appendBuffer(item.chunks[appended++]);
      } else if (item.done) {
        item.listeners.delete(next);
        source.endOfStream();
      }
    };
    buffer.addEventListener("updateend", next);
    item.listeners.add(next);
    next();
  }

  private speakWithBrowser(item: Item): void {
    if (typeof speechSynthesis === "undefined") {
      this.callbacks.onBrowserVoiceMissing(item.language);
      return this.dropAnswer();
    }
    const prefix = item.language;
    const voices = speechSynthesis.getVoices().filter((voice) => voice.lang.toLowerCase().startsWith(prefix));
    if (voices.length === 0) {
      this.callbacks.onBrowserVoiceMissing(item.language);
      return this.dropAnswer();
    }
    const utterance = new SpeechSynthesisUtterance(item.text);
    utterance.lang = bcp47(item.language);
    utterance.voice = voices.find((voice) => voice.localService) ?? voices[0];
    utterance.onstart = () => {
      this.browserVoice = true;
      this.onPlaying();
    };
    utterance.onend = () => this.finishCurrent();
    utterance.onerror = () => this.finishCurrent();
    speechSynthesis.speak(utterance);
  }

  /** Nothing can be spoken for this answer (no voice on this device): captions only. */
  private dropAnswer(): void {
    if (this.current?.clip) this.endClip();
    this.answer?.abort.abort();
    this.answer = null;
    this.queue = [];
    this.current = null;
    this.speaking = false;
    this.emit();
  }

  private onPlaying(): void {
    if (this.answer && !this.answer.firstAudio) {
      this.answer.firstAudio = true;
      performance.mark("voice:first-audio");
    }
    this.speaking = true;
    this.emit();
  }

  private revoke(): void {
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.objectUrl = null;
  }

  private emit(): void {
    this.callbacks.onState({
      speaking: this.speaking,
      active: this.answer !== null || (this.current !== null && !this.current.clip),
    });
  }
}

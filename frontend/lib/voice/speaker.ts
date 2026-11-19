import { VoiceHttpError, streamSpeech } from "@/services/voice";
import type { ChatLanguage } from "@/services/types";

import { spaceArabicLatin } from "@/lib/text/spacing";
import { LevelMeter } from "./levels";
import { SentenceSplitter } from "./sentences";
import {
  type Alignment,
  type TimedToken,
  type Token,
  progressAt,
  proportionalTimes,
  sourceIndex,
  timeTokens,
  tokenAt,
  tokenize,
} from "./timing";
import type { LiveProgress, VoiceRecord } from "./transcript";

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
 *
 * Word timing (the transcript's "lighting up"): every sentence arrives with character
 * timestamps (NDJSON from /voice/speak); `progress()` maps the REAL `audio.currentTime` of
 * the sentence playing now to words of the answer (offsets into its text). The browser voice
 * uses `boundary` events, or a proportional estimate when the browser sends none. Each voiced
 * answer (or the greeting) is an "owner"; `onRecord` reports live / done / stopped.
 */

/** Browser voices speak roughly this many characters per second (estimate only). */
const BROWSER_CHARS_PER_SECOND = 14;

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
  /** What the voice is asked to say (with "و React" spacing). */
  text: string;
  /** The same sentence as it appears in the owner's text, and where it starts there. */
  source: string;
  offset: number;
  /** Words of `source`, with offsets in the owner's text. */
  tokens: Token[];
  alignment: Alignment;
  timed: TimedToken[] | null;
  timedChars: number;
  /** Browser voice: the latest boundary (offset in the owner's text) and when it started. */
  boundary: number | null;
  startedAt: number;
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

/** What is being voiced: an answer (`answer:<id>`) or the greeting. */
type Owner = { id: string; text: string; cursor: number; litUpTo: number };

type Callbacks = {
  onState: (state: SpeakerState) => void;
  /** An owner started, finished, or was stopped (for the transcript's highlighting). */
  onRecord?: (owner: string, record: VoiceRecord) => void;
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
  private owner: Owner | null = null;

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
    alignment: Alignment | null = null,
  ): Promise<"playing" | "blocked" | "failed"> {
    const audio = this.audio;
    if (!audio) return "failed";
    this.stop();
    const token = ++this.clipToken;
    if (viaGesture) this.unlock();
    const item: Item = {
      ...newItem(text, text, 0, language, alignment),
      done: true,
      started: true,
      clip: true,
    };
    this.current = item;
    this.clipEnded = onEnd;
    this.startOwner("greeting", text);
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
    if (this.owner) this.callbacks.onRecord?.(this.owner.id, { state: "pending" });
    this.owner = null; // not played (yet): the greeting stays "pending"
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

  begin(language: ChatLanguage, owner = "answer"): void {
    this.stop();
    this.startOwner(owner, "");
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
    if (this.owner) this.owner.text += text;
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
    this.endOwner("stopped");
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
    // Where this sentence sits in the answer text (the splitter trims whitespace).
    const source = text.trim();
    const owner = this.owner;
    let offset = owner ? owner.text.indexOf(source, owner.cursor) : 0;
    if (offset < 0) offset = owner?.cursor ?? 0;
    if (owner) owner.cursor = offset + source.length;
    // "وReact" would be read as one word; both voices get "و React".
    const item = newItem(spaceArabicLatin(source), source, offset, answer.language, null);
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
      await streamSpeech(
        item.text,
        item.language,
        answer.abort.signal,
        (bytes) => {
          item.chunks.push(bytes);
          notify(item);
        },
        (alignment) => {
          item.alignment.chars.push(...alignment.chars);
          item.alignment.starts.push(...alignment.starts);
          item.alignment.ends.push(...alignment.ends);
        },
      );
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
        this.endOwner("done");
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
    const finished = this.current;
    if (this.owner) {
      this.owner.litUpTo = Math.max(this.owner.litUpTo, finished.offset + finished.source.length);
    }
    if (finished.clip) {
      this.endOwner("done");
      this.endClip();
    }
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
      item.startedAt = performance.now();
      this.browserVoice = true;
      this.onPlaying();
    };
    utterance.onboundary = (event) => {
      if (event.name && event.name !== "word") return;
      item.boundary = item.offset + sourceIndex(item.source, item.text, event.charIndex);
    };
    utterance.onend = () => this.finishCurrent();
    utterance.onerror = () => this.finishCurrent();
    speechSynthesis.speak(utterance);
  }

  /** Nothing can be spoken for this answer (no voice on this device): captions only. */
  private dropAnswer(): void {
    this.endOwner("done"); // nothing could be voiced: the text is shown fully bright
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

  // --------------------------------------------------------------------- word timing

  private startOwner(id: string, text: string): void {
    this.owner = { id, text, cursor: 0, litUpTo: 0 };
    this.callbacks.onRecord?.(id, { state: "live" });
  }

  private endOwner(how: "done" | "stopped"): void {
    const owner = this.owner;
    if (!owner) return;
    const litUpTo = this.progress()?.litUpTo ?? owner.litUpTo;
    this.owner = null;
    this.callbacks.onRecord?.(owner.id, how === "done" ? { state: "done" } : { state: "stopped", litUpTo });
  }

  /** Word timing of the item playing now (recomputed as its alignment grows). */
  private timesFor(item: Item, duration: number): TimedToken[] {
    if (item.alignment.chars.length) {
      if (!item.timed || item.timedChars !== item.alignment.chars.length) {
        item.timed = timeTokens(item.tokens, item.alignment);
        item.timedChars = item.alignment.chars.length;
      }
      return item.timed;
    }
    return proportionalTimes(item.tokens, duration);
  }

  /**
   * How far the current owner has been spoken: words up to `litUpTo` (an offset in its text)
   * are lit, `current` is the word being spoken. Call every animation frame.
   */
  progress(): (LiveProgress & { owner: string }) | null {
    const owner = this.owner;
    if (!owner) return null;
    const item = this.current;
    if (!item || !item.started) return { owner: owner.id, litUpTo: owner.litUpTo, current: null };
    let live: LiveProgress;
    if (this.browserVoice) {
      if (item.boundary !== null) {
        const word = tokenAt(item.tokens, item.boundary);
        live = { litUpTo: word?.end ?? item.offset, current: word };
      } else {
        const elapsed = (performance.now() - item.startedAt) / 1000;
        const estimate = Math.max(1, item.text.length / BROWSER_CHARS_PER_SECOND);
        live = progressAt(proportionalTimes(item.tokens, estimate), elapsed);
      }
    } else if (this.audio) {
      const duration = Number.isFinite(this.audio.duration) ? this.audio.duration : item.text.length / 14;
      live = progressAt(this.timesFor(item, duration), this.audio.currentTime);
    } else {
      live = { litUpTo: owner.litUpTo, current: null };
    }
    return {
      owner: owner.id,
      litUpTo: Math.max(owner.litUpTo, live.litUpTo),
      current: live.current ? { start: live.current.start, end: live.current.end } : null,
    };
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

function newItem(
  text: string,
  source: string,
  offset: number,
  language: ChatLanguage,
  alignment: Alignment | null,
): Item {
  return {
    text,
    source,
    offset,
    tokens: tokenize(source, offset),
    alignment: alignment ?? { chars: [], starts: [], ends: [] },
    timed: null,
    timedChars: 0,
    boundary: null,
    startedAt: 0,
    language,
    chunks: [],
    done: false,
    failed: false,
    started: false,
    listeners: new Set(),
  };
}

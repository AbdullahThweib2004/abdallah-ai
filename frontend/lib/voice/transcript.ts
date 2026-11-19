/**
 * How a transcript entry is lit, from what the voice did with it.
 *
 * - Not voiced at all (voice muted or unavailable, browser has no voice): fully bright.
 * - Being voiced: words up to `litUpTo` are bright, the word being spoken glows, the rest is
 *   dimmed (still readable). Text that streams in before its audio is dimmed until spoken.
 * - Voiced to the end: bright.
 * - Stopped (Stop, barge-in): what was spoken stays bright, the rest stays dimmed.
 *
 * No imports: this module also runs directly under `node --test`.
 */

export type VoiceRecord =
  | { state: "pending" } // will be voiced (e.g. the greeting waiting for a gesture)
  | { state: "live" }
  | { state: "done" }
  | { state: "stopped"; litUpTo: number };

export type LiveProgress = { litUpTo: number; current: { start: number; end: number } | null };

export type EntryView =
  | { mode: "bright" }
  | { mode: "lit"; litUpTo: number; current: { start: number; end: number } | null; stopped: boolean };

export function entryView(record: VoiceRecord | undefined, live: LiveProgress | null): EntryView {
  if (!record || record.state === "done") return { mode: "bright" };
  if (record.state === "stopped") return { mode: "lit", litUpTo: record.litUpTo, current: null, stopped: true };
  if (record.state === "pending") return { mode: "lit", litUpTo: 0, current: null, stopped: false };
  return { mode: "lit", litUpTo: live?.litUpTo ?? 0, current: live?.current ?? null, stopped: false };
}

export type WordState = "spoken" | "current" | "pending";

/** State of the word [start, end) under `view`. */
export function wordState(view: EntryView, start: number, end: number): WordState {
  if (view.mode === "bright") return "spoken";
  if (view.current && start < view.current.end && end > view.current.start) return "current";
  return end <= view.litUpTo ? "spoken" : "pending";
}

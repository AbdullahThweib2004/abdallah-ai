/**
 * Word timing for the "lighting up" transcript: which word of an answer is being spoken now.
 *
 * - Tokens are whitespace-separated words with their character offsets in the answer text
 *   (punctuation stays attached; "97.15" is one word).
 * - The provider's character alignment covers the SPOKEN text, which the server may have
 *   cleaned (an email becomes "his email", "وReact" becomes "و React"). Display and spoken
 *   characters are matched after normalization (case, punctuation, Arabic diacritics), in
 *   order, within a small look-ahead window; words without a match get interpolated times.
 * - Without any alignment (browser voice without boundary events) times are proportional to
 *   word length over the utterance duration.
 *
 * No imports: this module also runs directly under `node --test` (see tests/).
 */

export type Alignment = { chars: string[]; starts: number[]; ends: number[] };
/** A word: `start`/`end` are character offsets in the source text (end exclusive). */
export type Token = { text: string; start: number; end: number };
/** A word with its spoken interval, in seconds from the start of its audio. */
export type TimedToken = Token & { t0: number; t1: number };

const LOOKAHEAD = 24;
const DIACRITICS = /[ً-ٰٟـ]/;
const DROPPED = /[\s\p{P}\p{S}]/u;
const FOLD: Record<string, string> = { "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي" };

/** Normalized form of one character, or "" when it carries no sound (space, punctuation). */
export function normalizeChar(char: string): string {
  if (DROPPED.test(char) || DIACRITICS.test(char)) return "";
  const lower = char.toLowerCase();
  return FOLD[lower] ?? lower;
}

/** Words of `text` with offsets, shifted by `base`. */
export function tokenize(text: string, base = 0): Token[] {
  const tokens: Token[] = [];
  for (const match of text.matchAll(/\S+/g)) {
    const start = base + (match.index ?? 0);
    tokens.push({ text: match[0], start, end: start + match[0].length });
  }
  return tokens;
}

/** Spread [from, to] over the tokens in proportion to their length (a space counts as 1). */
function spread(tokens: Token[], from: number, to: number): { t0: number; t1: number }[] {
  const weights = tokens.map((token) => token.text.length + 1);
  const total = weights.reduce((sum, weight) => sum + weight, 0) || 1;
  let at = from;
  return weights.map((weight) => {
    const t0 = at;
    at += ((to - from) * weight) / total;
    return { t0, t1: at };
  });
}

/** Proportional times: the fallback when no alignment exists. */
export function proportionalTimes(tokens: Token[], duration: number, startAt = 0): TimedToken[] {
  return spread(tokens, startAt, startAt + duration).map((times, i) => ({ ...tokens[i], ...times }));
}

/**
 * Times for `tokens` from a character alignment of the spoken text (same sentence).
 * Monotonic: a word never starts before the previous one.
 */
export function timeTokens(tokens: Token[], alignment: Alignment): TimedToken[] {
  const spoken: { ch: string; t0: number; t1: number }[] = [];
  alignment.chars.forEach((char, i) => {
    const ch = normalizeChar(char);
    if (ch) spoken.push({ ch, t0: alignment.starts[i], t1: alignment.ends[i] });
  });
  const matched: ({ t0: number; t1: number } | null)[] = tokens.map(() => null);
  let next = 0;
  tokens.forEach((token, index) => {
    for (const char of token.text) {
      const ch = normalizeChar(char);
      if (!ch) continue;
      for (let j = next; j < Math.min(spoken.length, next + LOOKAHEAD); j++) {
        if (spoken[j].ch !== ch) continue;
        const span = matched[index];
        matched[index] = span
          ? { t0: Math.min(span.t0, spoken[j].t0), t1: Math.max(span.t1, spoken[j].t1) }
          : { t0: spoken[j].t0, t1: spoken[j].t1 };
        next = j + 1;
        break;
      }
    }
  });
  const end = alignment.ends.length ? alignment.ends[alignment.ends.length - 1] : 0;
  if (matched.every((span) => span === null)) return proportionalTimes(tokens, end);

  // Interpolate runs of unmatched words between their matched neighbours.
  const result: TimedToken[] = [];
  let index = 0;
  while (index < tokens.length) {
    const span = matched[index];
    if (span) {
      const t0 = Math.max(span.t0, result.length ? result[result.length - 1].t0 : 0);
      result.push({ ...tokens[index], t0, t1: Math.max(span.t1, t0) });
      index++;
      continue;
    }
    let stop = index;
    while (stop < tokens.length && !matched[stop]) stop++;
    const from = result.length ? result[result.length - 1].t1 : 0;
    const to = stop < tokens.length ? Math.max(from, matched[stop]!.t0) : Math.max(from, end);
    const run = tokens.slice(index, stop);
    spread(run, from, to).forEach((times, i) => result.push({ ...run[i], ...times }));
    index = stop;
  }
  return result;
}

/** Shift every token's character offsets by `delta` (sentence → answer offsets). */
export function offsetTokens<T extends Token>(tokens: T[], delta: number): T[] {
  return tokens.map((token) => ({ ...token, start: token.start + delta, end: token.end + delta }));
}

/**
 * Highlight state at time `t` (seconds into this audio): every word that has STARTED is lit
 * (`litUpTo` = its end offset), the word being spoken is `current` (null in a pause).
 */
export function progressAt(tokens: TimedToken[], t: number): { litUpTo: number; current: Token | null } {
  let litUpTo = tokens.length ? tokens[0].start : 0;
  let current: Token | null = null;
  for (const token of tokens) {
    if (token.t0 > t) break;
    litUpTo = token.end;
    current = t < token.t1 ? token : null;
  }
  return { litUpTo, current };
}

/** The word containing character `offset`, else the next one (browser-voice boundaries). */
export function tokenAt(tokens: Token[], offset: number): Token | null {
  for (const token of tokens) if (offset < token.end) return token;
  return tokens.length ? tokens[tokens.length - 1] : null;
}

/**
 * Map an index in `spokenText` (the source with extra spaces inserted, e.g. "و React") back to
 * the source string: inserted characters are skipped.
 */
export function sourceIndex(source: string, spokenText: string, spokenIndex: number): number {
  let i = 0;
  let j = 0;
  while (j < spokenIndex && j < spokenText.length) {
    if (i < source.length && source[i] === spokenText[j]) i++;
    j++;
  }
  return i;
}

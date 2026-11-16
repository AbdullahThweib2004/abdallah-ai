/**
 * Split a streamed answer into sentences, so each one can be synthesized as soon as it is
 * complete. Arabic- and English-aware:
 *
 * - Ends at `.` `!` `?` `؟` `…` (and `،` once a clause is long enough to be worth sending)
 *   followed by whitespace, or at a line break. Closing quotes/brackets stay with the sentence.
 * - A terminator at the very end of the buffer is not trusted until the next character
 *   arrives: "97." may still become "97.15".
 * - Never splits decimals ("97.15"), dotted names ("Node.js", "ASP.NET"), initials
 *   ("J. Smith") or common abbreviations ("e.g.", "Dr.", "B.Sc.").
 *
 * No imports: this module also runs directly under `node --test` (see tests/).
 */

const TERMINATORS = new Set([".", "!", "?", "؟", "…"]);
const ARABIC_COMMA = "،";
// Shorter clauses wait for more text: tiny chunks sound choppy.
const MIN_COMMA_CLAUSE = 40;
// The backend accepts 600 characters; long run-ons are cut at a space well before that.
const MAX_SENTENCE = 400;
const CLOSERS = new Set(['"', "'", "”", "’", ")", "]", "»"]);

const ABBREVIATIONS = new Set([
  "e.g",
  "i.e",
  "etc",
  "vs",
  "approx",
  "dr",
  "mr",
  "mrs",
  "ms",
  "prof",
  "jr",
  "sr",
  "st",
  "inc",
  "ltd",
  "co",
  "fig",
  "dept",
  "b.sc",
  "m.sc",
  "ph.d",
  "u.s",
  "u.k",
]);

function isSpace(char: string | undefined): boolean {
  return char !== undefined && /\s/.test(char);
}

/** The word right before index `dot` (letters and inner dots), lowercased. */
function wordBefore(text: string, dot: number): string {
  let start = dot;
  while (start > 0 && /[\p{L}\p{N}.]/u.test(text[start - 1])) start--;
  return text.slice(start, dot).toLowerCase();
}

function isAbbreviation(text: string, dot: number): boolean {
  const word = wordBefore(text, dot);
  if (!word) return false;
  if (ABBREVIATIONS.has(word)) return true;
  // A single Latin letter is an initial ("J. Smith"); "x.y" patterns are dotted abbreviations.
  if (/^[a-z]$/.test(word) && /[A-Z]/.test(text[dot - 1])) return true;
  return /^(?:[a-z]\.)+[a-z]$/.test(word);
}

export class SentenceSplitter {
  private buffer = "";

  /** Add streamed text; returns the sentences it completed (trimmed, non-empty). */
  push(text: string): string[] {
    this.buffer += text;
    const sentences: string[] = [];
    let start = 0;
    let index = 0;
    while (index < this.buffer.length) {
      const end = this.boundaryAt(index, start);
      if (end !== null) {
        const sentence = this.buffer.slice(start, end).trim();
        if (sentence) sentences.push(sentence);
        start = end;
        index = end;
        continue;
      }
      if (index - start >= MAX_SENTENCE) {
        const cut = this.buffer.lastIndexOf(" ", index);
        const end = cut > start ? cut : index;
        const piece = this.buffer.slice(start, end).trim();
        if (piece) sentences.push(piece);
        start = end;
      }
      index++;
    }
    this.buffer = this.buffer.slice(start);
    return sentences;
  }

  /** The rest of the answer once the stream has ended. */
  flush(): string[] {
    const rest = this.buffer.trim();
    this.buffer = "";
    return rest ? [rest] : [];
  }

  /** If a sentence ends at `index`, the position right after it (closers included). */
  private boundaryAt(index: number, start: number): number | null {
    const text = this.buffer;
    const char = text[index];
    if (char === "\n") return index + 1;
    const isComma = char === ARABIC_COMMA;
    if (!TERMINATORS.has(char) && !isComma) return null;
    if (isComma && index - start < MIN_COMMA_CLAUSE) return null;

    let end = index + 1;
    // "..." and "?!" end together.
    while (end < text.length && (TERMINATORS.has(text[end]) || CLOSERS.has(text[end]))) end++;
    // Wait for the next character: the boundary needs whitespace after it.
    if (end >= text.length || !isSpace(text[end])) return null;
    if (char === "." && end === index + 1) {
      if (isAbbreviation(text, index)) return null;
      // A list number at the start of a sentence ("1. First") is not a sentence.
      const word = wordBefore(text, index);
      if (/^\d{1,2}$/.test(word) && !text.slice(start, index - word.length).trim()) return null;
    }
    return end;
  }
}

/** Split a complete text (convenience for tests and non-streamed answers). */
export function splitSentences(text: string): string[] {
  const splitter = new SentenceSplitter();
  return [...splitter.push(text), ...splitter.flush()];
}

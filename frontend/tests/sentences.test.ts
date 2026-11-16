// Run with `npm test` (Node's built-in test runner; Node strips the TypeScript types).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { SentenceSplitter, splitSentences } from "../lib/voice/sentences.ts";

/** Feed `text` in small chunks, like streamed tokens, and collect every sentence. */
function streamed(text: string, chunk = 3): string[] {
  const splitter = new SentenceSplitter();
  const out: string[] = [];
  for (let i = 0; i < text.length; i += chunk) out.push(...splitter.push(text.slice(i, i + chunk)));
  return [...out, ...splitter.flush()];
}

describe("English", () => {
  it("splits on . ! ?", () => {
    assert.deepEqual(splitSentences("He built Nawa. It is fast! Want details? Ask me."), [
      "He built Nawa.",
      "It is fast!",
      "Want details?",
      "Ask me.",
    ]);
  });

  it("emits a sentence only once the next character confirms the boundary", () => {
    const splitter = new SentenceSplitter();
    assert.deepEqual(splitter.push("It reached 97."), []);
    assert.deepEqual(splitter.push("15 percent. Next"), ["It reached 97.15 percent."]);
    assert.deepEqual(splitter.flush(), ["Next"]);
  });

  it("keeps abbreviations, initials, dotted names and list numbers", () => {
    assert.deepEqual(
      splitSentences("He used tools, e.g. FastAPI and Node.js, with Dr. Smith and J. Doe. Done."),
      ["He used tools, e.g. FastAPI and Node.js, with Dr. Smith and J. Doe.", "Done."],
    );
    assert.deepEqual(splitSentences("He holds a B.Sc. in CS. He likes ASP.NET too."), [
      "He holds a B.Sc. in CS.",
      "He likes ASP.NET too.",
    ]);
    assert.deepEqual(splitSentences("1. First item is here. 2. Second."), ["1. First item is here.", "2. Second."]);
  });

  it("keeps closing quotes and brackets, and groups ?! and ...", () => {
    assert.deepEqual(splitSentences('He said "it works." Really?! Yes... Fine (mostly.) End'), [
      'He said "it works."',
      "Really?!",
      "Yes...",
      "Fine (mostly.)",
      "End",
    ]);
  });

  it("splits on line breaks and drops empty pieces", () => {
    assert.deepEqual(splitSentences("Projects\n\nNawa is one.\n"), ["Projects", "Nawa is one."]);
  });

  it("gives the same result however the text is chunked", () => {
    const text = "Accuracy was 97.15 percent. He wrote it in C++. Version 2.0 shipped! Done?";
    const expected = splitSentences(text);
    for (const size of [1, 2, 5, 13]) assert.deepEqual(streamed(text, size), expected);
  });

  it("cuts very long run-ons at a space", () => {
    const words = Array.from({ length: 150 }, (_, i) => `word${i}`).join(" ");
    const pieces = splitSentences(words);
    assert.ok(pieces.length >= 2);
    for (const piece of pieces) assert.ok(piece.length <= 400, `${piece.length} chars`);
    assert.equal(pieces.join(" "), words);
  });
});

describe("Arabic", () => {
  it("splits on . ؟ !", () => {
    assert.deepEqual(splitSentences("بنى عبدالله مشروع Nawa. هل تريد التفاصيل؟ إنه سريع! شكراً"), [
      "بنى عبدالله مشروع Nawa.",
      "هل تريد التفاصيل؟",
      "إنه سريع!",
      "شكراً",
    ]);
  });

  it("splits on the Arabic comma only after a long clause", () => {
    assert.deepEqual(splitSentences("نعم، بالتأكيد."), ["نعم، بالتأكيد."]);
    const long = "عمل عبدالله على نظام استرجاع معلومات متقدم للمستندات التقنية، ثم أضاف واجهة محادثة.";
    assert.deepEqual(splitSentences(long), [
      "عمل عبدالله على نظام استرجاع معلومات متقدم للمستندات التقنية،",
      "ثم أضاف واجهة محادثة.",
    ]);
  });

  it("does not split Arabic decimals or numbers", () => {
    assert.deepEqual(splitSentences("بلغت الدقة 97.15 بالمئة. وهذا جيد."), [
      "بلغت الدقة 97.15 بالمئة.",
      "وهذا جيد.",
    ]);
  });
});

describe("mixed Arabic and English", () => {
  it("handles English terms inside Arabic sentences", () => {
    const text = "استخدم FastAPI و Node.js في المشروع. ثم كتب محرك C++ اسمه Nawa؟ نعم. Next.js أيضاً.";
    assert.deepEqual(splitSentences(text), [
      "استخدم FastAPI و Node.js في المشروع.",
      "ثم كتب محرك C++ اسمه Nawa؟",
      "نعم.",
      "Next.js أيضاً.",
    ]);
    assert.deepEqual(streamed(text, 2), splitSentences(text));
  });

  it("switches language between sentences", () => {
    assert.deepEqual(splitSentences("He built RAG systems. وبنى أيضاً محرك استدلال. Ask more!"), [
      "He built RAG systems.",
      "وبنى أيضاً محرك استدلال.",
      "Ask more!",
    ]);
  });
});

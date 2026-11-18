import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { spaceArabicLatin } from "../lib/text/spacing.ts";

describe("spaceArabicLatin", () => {
  it("inserts a space between an Arabic letter and a following Latin letter", () => {
    assert.equal(spaceArabicLatin("استخدم Python وReact وFastAPI"), "استخدم Python و React و FastAPI");
    assert.equal(spaceArabicLatin("بـMCP"), "بـ MCP");
    assert.equal(spaceArabicLatin("عبرLinkedIn"), "عبر LinkedIn");
  });

  it("leaves correct text, digits, punctuation and English alone", () => {
    for (const text of ["و React", "بنسبة 97.15%", "Node.js، و C++", "He built Nawa.", "الإصدار 2"]) {
      assert.equal(spaceArabicLatin(text), text);
    }
  });
});

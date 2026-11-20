import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

// The transcript's word states, read from the stylesheet itself so the numbers cannot drift.
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

function token(name: string): string {
  const match = css.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, "i"));
  assert.ok(match, `--color-${name} is defined`);
  return match[1];
}

function rule(selector: string, from = 0): string {
  const start = css.indexOf(`${selector} {`, from);
  assert.ok(start >= 0, `rule ${selector}`);
  return css.slice(start, css.indexOf("}", start));
}

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const channel = (c: number) => ((c /= 255) <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const luminance = ([r, g, b]: number[]) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
function contrast(a: number[], b: number[]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
/** The panel: 92 % ink-850 over the page (ink-950). */
const panel = rgb(token("ink-850")).map((c, i) => c * 0.92 + rgb(token("ink-950"))[i] * 0.08);

describe("transcript word colours", () => {
  const dim = rule(".transcript-text .tw");
  const current = rule('.transcript-text .tw[data-state="current"]');

  it("dimmed words stay readable on the panel (WCAG AA, ≥ 4.5:1)", () => {
    assert.match(dim, /color: var\(--color-mist-500\)/);
    assert.equal(token("mist-500").toLowerCase(), "#86837a");
    assert.ok(contrast(rgb(token("mist-500")), panel) >= 4.5, `${contrast(rgb(token("mist-500")), panel).toFixed(2)}:1`);
  });

  it("spoken words stand clearly apart from dimmed ones (≥ 3:1)", () => {
    assert.match(css, /\.transcript-text \.tw\[data-state="spoken"\],[^{]*\{\s*color: var\(--color-mist-50\)/);
    assert.ok(contrast(rgb(token("mist-50")), rgb(token("mist-500"))) >= 3);
  });

  it("the word being spoken is amber with a glow, readable on the panel", () => {
    assert.match(current, /color: var\(--color-accent\)/);
    assert.match(current, /text-shadow:/);
    assert.equal(token("accent").toLowerCase(), "#f0b35b");
    assert.ok(contrast(rgb(token("accent")), panel) >= 4.5);
  });

  it("reduced motion keeps the amber but drops the glow and the fade", () => {
    const reduce = css.indexOf("@media (prefers-reduced-motion: reduce) {\n  .transcript-text");
    assert.ok(reduce >= 0);
    assert.match(rule('.transcript-text .tw[data-state="current"]', reduce), /text-shadow: none/);
    const motion = css.indexOf("@media (prefers-reduced-motion: no-preference) {\n  .transcript-text");
    assert.ok(motion >= 0, "the transition only exists for no-preference");
    assert.equal(css.slice(0, motion).match(/\.transcript-text \.tw \{[^}]*transition/), null);
  });
});

import type { ReactNode } from "react";

// A Latin run inside Arabic text: starts with a Latin letter or digit and continues over Latin
// letters, digits, spaces and the punctuation that appears inside names and terms
// ("AI-Powered", "C++20", "Recall@5 = 1.000", "Assistant (Desktop)", "7.4 µs"). Non-breaking hyphens and
// narrow/no-break spaces are included because gpt-oss uses them.
const LATIN_RUN = /[A-Za-z0-9][A-Za-z0-9 .,:;+#&@/'’_()%µ=\u00A0\u2009\u202F\u2010-\u2014-]*/g;
const TRAILING = /[ .,:;(\u00A0\u2009\u202F]+$/;

function count(text: string, char: string): number {
  return text.split(char).length - 1;
}

/**
 * Keep sentence punctuation, a trailing opening bracket and unmatched closing brackets outside
 * the isolated run, so they stay in the surrounding right-to-left context:
 * "(Smart System (Desktop))،" isolates "Smart System (Desktop)"; "PostgreSQL (مع …)" isolates
 * "PostgreSQL".
 */
function trimRun(run: string): string {
  let trimmed = run.replace(TRAILING, "");
  while (trimmed.endsWith(")") && count(trimmed, ")") > count(trimmed, "(")) {
    trimmed = trimmed.slice(0, -1).replace(TRAILING, "");
  }
  return trimmed;
}

/**
 * Wrap each Latin run of a right-to-left text in <bdi dir="ltr"> (unicode-bidi: isolate), so
 * terms that end in neutral characters render in order: without it, "بلغة C++." shows as "++C".
 */
export function isolateLatin(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(LATIN_RUN)) {
    const run = trimRun(match[0]);
    const start = match.index;
    if (start > last) parts.push(text.slice(last, start));
    parts.push(
      <bdi key={start} dir="ltr">
        {run}
      </bdi>,
    );
    last = start + run.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

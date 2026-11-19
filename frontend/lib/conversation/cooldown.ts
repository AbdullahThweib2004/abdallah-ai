// "Busy right now, try again in N seconds": pure helpers for the provider-limit countdown,
// unit-tested in `tests/cooldown.test.ts`.

/** Whole seconds left until `until` (ms since epoch), never negative; 1.2 s left shows "2". */
export function secondsLeft(until: number, now: number): number {
  return Math.max(0, Math.ceil((until - now) / 1000));
}

/** When the server said "busy, retry after N s", the moment the composer may send again. */
export function cooldownUntil(retryAfterSeconds: number, now: number): number {
  const seconds = Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0 ? retryAfterSeconds : 20;
  return now + Math.min(seconds, 3600) * 1000;
}

/** One message per CLDR plural category; `{n}` is replaced by the number of seconds. */
export type PluralMessages = { one: string; two: string; few: string; many: string; other: string };

/** The busy message in the right plural form (Arabic has distinct one/two/few/many forms). */
export function busyMessage(messages: PluralMessages, locale: string, seconds: number): string {
  const category = new Intl.PluralRules(locale).select(seconds);
  const template = category in messages ? messages[category as keyof PluralMessages] : messages.other;
  return template.replace("{n}", String(seconds));
}

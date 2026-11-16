/** Cookie holding the speaker toggle: "on" | "off". Absent = the visitor never chose. */
export const VOICE_REPLIES_COOKIE = "voice_replies";

const ONE_YEAR = 60 * 60 * 24 * 365;

export type VoiceRepliesPreference = "on" | "off" | null;

export function parseVoiceReplies(value: string | undefined): VoiceRepliesPreference {
  return value === "on" || value === "off" ? value : null;
}

/** Browser-side write; the server reads it on the next page load (no hydration flash). */
export function saveVoiceReplies(on: boolean): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${VOICE_REPLIES_COOKIE}=${on ? "on" : "off"}; Path=/; Max-Age=${ONE_YEAR}; SameSite=Lax${secure}`;
}

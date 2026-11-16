import { API_BASE_URL } from "./api";
import type { ChatLanguage } from "./types";

export type VoiceErrorCode =
  | "unsupported_type"
  | "too_large"
  | "too_long"
  | "no_speech"
  | "invalid_request"
  | "nothing_to_say"
  | "rate_limited"
  | "daily_limit"
  | "daily_cap"
  | "tts_quota"
  | "stt_unavailable"
  | "tts_unavailable";

export type VoiceConfig = {
  stt: { provider: "fake" | "groq" | "none"; max_seconds: number; max_bytes: number };
  tts: { provider: "fake" | "browser" | "elevenlabs"; max_chars: number };
};

export type Transcript = { text: string; language: ChatLanguage; duration_ms: number };

/** A failed voice request. `code` is null when the server sent no usable error body. */
export class VoiceHttpError extends Error {
  constructor(
    public readonly status: number | null,
    public readonly code: VoiceErrorCode | null,
  ) {
    super(`Voice request failed (${status ?? "network"}${code ? `, ${code}` : ""})`);
    this.name = "VoiceHttpError";
  }
}

async function errorFrom(response: Response): Promise<VoiceHttpError> {
  let code: VoiceErrorCode | null = null;
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "code" in body && typeof body.code === "string") {
      code = body.code as VoiceErrorCode;
    }
  } catch {
    // not JSON
  }
  return new VoiceHttpError(response.status, code);
}

async function request(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/voice${path}`, init);
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new VoiceHttpError(null, null);
  }
  if (!response.ok) throw await errorFrom(response);
  return response;
}

export async function getVoiceConfig(signal?: AbortSignal): Promise<VoiceConfig> {
  const response = await request("/config", { signal, headers: { Accept: "application/json" } });
  return (await response.json()) as VoiceConfig;
}

/** Upload one recorded clip. Audio leaves the browser only here, and only after a click. */
export async function transcribe(
  audio: Blob,
  languageHint: ChatLanguage | "auto",
  signal?: AbortSignal,
): Promise<Transcript> {
  const extension = audio.type.includes("ogg") ? "ogg" : audio.type.includes("mp4") ? "m4a" : "webm";
  const form = new FormData();
  form.append("audio", audio, `clip.${extension}`);
  form.append("language_hint", languageHint);
  const response = await request("/transcribe", { method: "POST", body: form, signal });
  return (await response.json()) as Transcript;
}

/** Start synthesizing one sentence; the body streams `audio/mpeg`. */
export function fetchSpeech(text: string, language: ChatLanguage, signal: AbortSignal): Promise<Response> {
  return request("/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "audio/mpeg" },
    body: JSON.stringify({ text, language }),
    signal,
  });
}

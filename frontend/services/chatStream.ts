import { API_BASE_URL } from "./api";
import type { ChatEvent, ChatRequest } from "./types";

/** Non-2xx answer (e.g. 429). `detail` is the server's friendly message when it sent one. */
export class ChatHttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string | null,
  ) {
    super(`Chat request failed with ${status}`);
    this.name = "ChatHttpError";
  }
}

function parseEvent(block: string): ChatEvent | null {
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  const payload: unknown = JSON.parse(data.join("\n"));
  if (typeof payload !== "object" || payload === null) return null;
  switch (name) {
    case "start":
    case "action":
    case "token":
    case "done":
    case "error":
      return { type: name, ...payload } as ChatEvent;
    default:
      return null; // ignore unknown events (forward compatible)
  }
}

/**
 * POST a chat turn and yield its Server-Sent Events as they arrive.
 * Abort with `signal` to stop; the caller keeps whatever text it already received.
 */
export async function* streamChat(request: ChatRequest, signal: AbortSignal): AsyncGenerator<ChatEvent> {
  const response = await fetch(`${API_BASE_URL}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok || !response.body) {
    let detail: string | null = null;
    try {
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // not JSON: fall back to the generic message
    }
    throw new ChatHttpError(response.status, detail);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const event = parseEvent(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (event) yield event;
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

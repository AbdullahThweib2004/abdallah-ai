# API

Source: `docs/spec.pdf` §7.4, §13.

The API is versioned under `/api/v1`. All requests and responses use strict Pydantic models.
Interactive docs are served by FastAPI at `/docs` while the backend is running.

## Routes

| Status | Method / endpoint | Purpose |
|---|---|---|
| ✅ Implemented | `GET /api/v1/health` | Service health and knowledge base status |
| ✅ Implemented | `GET /api/v1/profile` | Public profile assembled from `profile/` and `career/` documents |
| ✅ Implemented | `GET /api/v1/projects` | List public projects (featured first, then `order`) |
| ✅ Implemented | `GET /api/v1/projects/{project_id}` | One public project with its content sections |
| ✅ Implemented | `GET /api/v1/contact` | Public contact links (the future `open_public_link` allowlist) |
| Planned | `POST /api/v1/sessions` | Create a conversation session |
| ✅ Implemented | `POST /api/v1/chat` | Submit a text turn; the answer streams back as Server-Sent Events |
| ✅ Implemented | `POST /api/v1/voice/transcribe` | Transcribe an uploaded visitor audio clip (multipart) |
| ✅ Implemented | `POST /api/v1/voice/speak` | Stream speech (`audio/mpeg`) for one answer sentence (the spec's `voice/generate`) |
| ✅ Implemented | `GET /api/v1/voice/config` | Which speech providers are active, so the UI adapts |

Streaming routes may be added after the first prototype.

## Content source and errors

- The content endpoints are **read-only** and backed by the knowledge base, loaded **once at startup**.
  Only `status: approved` documents are loaded. Restart the backend after editing `knowledge_base/`.
- Nothing about Abdallah is hard-coded: every value comes from a document id plus a section heading
  (e.g. `about` → `## Headline`). Sections whose body is only `See frontmatter.` are dropped,
  but any extra text after that marker (such as a project's status note) is kept.
- Responses never include file paths, drafts or other internal fields.
- Errors are JSON: `{"detail": "<message>"}`.
  - `404` means an unknown or unapproved project id. `422` means a malformed id (it must be kebab-case).
  - `503` means the knowledge base failed to load (`"Portfolio content is temporarily unavailable."`).
    The API keeps running and `/health` reports `"knowledge_base": "error"`.

## `GET /api/v1/health`

```json
{ "status": "ok", "version": "0.1.0", "knowledge_base": "ok", "approved_documents": 15 }
```

## `GET /api/v1/profile`

```jsonc
{
  "name": "…",                    // "About <name>" title of the `about` document
  "name_ar": "…",                 // Arabic form of the name from the glossary, or null
  "headline": "…",                // about › Headline
  "summary_markdown": "…",        // about › Summary
  "location": "…",                // about › Location
  "languages": ["…"],             // about › Languages (comma-separated list)
  "intro": { "en": "…", "ar": "…" },  // about › Short self-introduction (English:/Arabic: lines)
  "ways_of_working": "…",         // about › Ways of working
  "education": [{ "heading": "…", "body_markdown": "…" }],          // education sections
  "experience": { "title": "…", "sections": [{ "heading": "…", "body_markdown": "…" }] },
  "skills": [{ "category": "…", "items": ["…"] }],                   // skills: one group per section
  "interests": { "summary": "…", "items": ["…"] },                  // interests prose + bullets
  "career_direction": [{ "heading": "…", "body_markdown": "…" }]    // goals sections
}
```

## `GET /api/v1/projects`

```json
[
  {
    "id": "ai-developer-assistant",
    "title": "…",
    "one_line_summary": "…",
    "project_status": "completed",
    "technologies": ["Python", "FastAPI"],
    "featured": true,
    "repository_url": "https://github.com/…",
    "demo_url": null,
    "tags": ["rag", "mcp"]
  }
]
```

## `GET /api/v1/projects/{project_id}`

Same fields as a list item, plus:

```json
{
  "last_reviewed": "2026-11-16",
  "sections": [{ "heading": "Problem", "body_markdown": "…" }]
}
```

## `GET /api/v1/contact`

```json
{ "links": [{ "link_id": "github", "label": "GitHub", "url": "https://github.com/…", "kind": "github" }] }
```

## `POST /api/v1/chat`

Streams one answer from Abdallah AI. The backend retrieves the knowledge-base chunks relevant
to the question (hybrid vector + keyword search, see `docs/architecture.md`) and builds the
prompt from `backend/app/agents/prompts/system_v5.md`, a small pinned identity context, the list of
valid project ids and those chunks only. The model also decides which card to show; the server
validates that request against the allowlist (see [UI actions](#ui-actions-allowlist)).

Request (strict, unknown fields → 422):

```json
{
  "message": "What's his strongest project?",
  "history": [
    { "role": "user", "content": "Hi" },
    { "role": "assistant", "content": "Hi! I'm Abdallah's AI version…" }
  ],
  "ui_language": "en"
}
```

| Field | Rules |
|---|---|
| `message` | trimmed, 1–800 characters |
| `history` | up to 8 previous turns, `role` is `user` or `assistant`, `content` 1–2000 characters |
| `ui_language` | `en` (default) or `ar`; used for error messages and as the fallback reply language |

Response: `text/event-stream`. Each event is `event: <name>` + `data: <json>`:

| Event | Data | When |
|---|---|---|
| `start` | `{"request_id": "…", "language": "en" \| "ar"}` | first; `language` is the reply language detected from the message (share of Arabic-script words ≥ 40 %), falling back to `ui_language` |
| `action` | `{"actions": [{"type": "show_project", "project_id": "…"}, …]}` | exactly once, **before the first `token`**; 0–2 validated card requests (`[]` = keep the current card) |
| `token` | `{"text": "…"}` | zero or more; the answer text only (reasoning output is discarded server-side) |
| `done` | `{"usage": {…}, "latency_ms": n, "sources": [{"doc_id", "title", "heading", "project_id"?}]}` | last, on success; `sources` are the retrieved sections (deduplicated, `project_id` only for projects) |
| `error` | `{"code": "unavailable" \| "timeout" \| "busy", "message": "…"}` | last, on failure; may follow some `token` events (keep the partial answer) |

Token text is plain text: markdown emphasis and code marks (`*`, backticks) are stripped
server-side. `error.message` is a friendly sentence in `ui_language` with no provider details. The server
never hangs: if the provider sends nothing for `LLM_TIMEOUT_SECONDS`, the stream ends with
`error` `timeout`.

```text
event: start
data: {"request_id": "5f0c…", "language": "en"}

event: token
data: {"text": "Abdallah"}

event: done
data: {"usage": {"input_tokens": 2105, "output_tokens": 84}, "latency_ms": 1430, "sources": [{"doc_id": "nawa-inference", "title": "Nawa: Neural Network Inference Engine in C++", "heading": "Results (only verified results)", "project_id": "nawa-inference"}]}
```

Limits (in-memory per process; a shared store replaces it in step 10). When a limit is hit the
response is **HTTP 429** JSON with a `Retry-After` header, not a stream:

```json
{ "detail": "You're sending messages quite fast. Please wait a minute and try again.", "code": "rate_limited" }
```

| Code | Limit (setting, default) |
|---|---|
| `rate_limited` | per IP per minute (`CHAT_RATE_PER_MINUTE`, 8) |
| `daily_limit` | per IP per UTC day (`CHAT_RATE_PER_DAY`, 60) |
| `daily_cap` | all visitors per UTC day (`CHAT_MAX_REQUESTS_PER_DAY`, 500) |

Only valid requests count towards the limits (a 422 does not). Logs contain request id,
language, model, token usage, latency, status and retrieval metadata (chunk ids, fused scores,
latency), never the message text or the API key.

## Voice

Speech goes through provider adapters (`backend/app/voice/`): STT `fake | groq` (Whisper over
the OpenAI-compatible `/audio/transcriptions`, reusing `LLM_BASE_URL`/`LLM_API_KEY`), TTS
`fake | browser | elevenlabs`. With `browser` the backend produces no audio at all: the
frontend speaks with the visitor's own `speechSynthesis`. Errors are JSON
`{"detail": "<English, for developers>", "code": "<code>"}`; the frontend shows its own
localized text per `code`.

**Privacy:** audio is read into memory (size-capped) and parsed in memory (FastAPI's
`UploadFile` is deliberately not used, since it spools parts over 1 MB to a temp file), sent to
the STT provider and dropped when the request ends. It is never written to disk or logged.
Transcripts are not logged either; logs carry bytes, duration, language and latency only.

### `GET /api/v1/voice/config`

```json
{ "stt": { "provider": "groq", "max_seconds": 30, "max_bytes": 2097152 },
  "tts": { "provider": "elevenlabs", "max_chars": 600 } }
```

`stt.provider` is `none` when the STT provider is misconfigured (voice input is then hidden
behind a "not available" message; text keeps working). `tts.provider` reports `browser` when
ElevenLabs is selected but has no key. No secrets, models or voice ids are exposed.

### `POST /api/v1/voice/transcribe`

`multipart/form-data` with exactly these fields (anything else → 422 `invalid_request`):

| Field | Rules |
|---|---|
| `audio` | file; webm/opus, ogg, wav or m4a; **≤ 2 MB** and **≤ 30 s**. The container is sniffed from its bytes and must match the declared type |
| `language_hint` | `auto` (default), `en` or `ar` |

Response `200`: `{"text": "What projects has Abdallah built with RAG?", "language": "en", "duration_ms": 2808}`.

- Duration is read from the container (WAV header, Ogg granule, WebM block timestamps, MP4
  `mvhd`) **before** any paid call; if a container has no usable timing, the provider's
  reported duration is checked afterwards.
- `auto`: if Whisper detects a language other than English or Arabic (short clips are
  sometimes taken for Persian or Urdu), the clip is transcribed once more in the language of
  the returned script.
- A vocabulary hint built from the knowledge base (name in both scripts, short project names,
  frequent technologies; ≤ 500 characters) is sent as Whisper's `prompt`, so names such as
  "عبدالله" and terms such as "RAG" are spelled correctly.
- Empty, silent (every segment `no_speech_prob` > 0.6), shorter than 0.3 s, or known Whisper
  silence hallucinations ("ترجمة نانسي قنقر", "Thanks for watching") → 422 `no_speech`.

### `POST /api/v1/voice/speak`

Request (strict): `{"text": "One answer sentence.", "language": "en"}`; `text` is trimmed,
1–600 characters, `language` is `en` or `ar`. Response: a streamed `audio/mpeg` body
(`Cache-Control: no-store`). The frontend calls it once per sentence as the answer streams.

Before synthesis the text is cleaned for speech (`app/voice/text.py`): URLs and bare domains
are dropped, email addresses become "his email" / "بريده الإلكتروني", markdown and
`[source: …]` labels are removed; decimals (`97.15`) and dotted terms (`Node.js`) are kept.
Nothing speakable left → 422 `nothing_to_say`.

Errors before the first audio byte return JSON (and the browser voice takes over for the rest
of that answer); a provider failure after audio started just ends the stream early.

### Voice errors and limits

| HTTP | `code` | Meaning |
|---|---|---|
| 413 | `too_large` / `too_long` | over 2 MB / over 30 s |
| 415 | `unsupported_type` | not webm/ogg/wav/m4a, or bytes do not match the declared type |
| 422 | `invalid_request`, `no_speech`, `nothing_to_say` | see above |
| 429 | `rate_limited`, `daily_limit`, `daily_cap` | per-IP/global request limits (with `Retry-After`) |
| 429 | `tts_quota` | the daily character budget is used up, or ElevenLabs reported its quota exhausted (server voice then stays off until the next UTC day) |
| 503 | `stt_unavailable` / `tts_unavailable` | provider down, misconfigured, or (`speak`) TTS is `browser` |

| Limit (setting, default) | Applies to |
|---|---|
| `VOICE_RATE_PER_MINUTE`, 6 | transcribe, per IP; daily limits shared with chat (`CHAT_RATE_PER_DAY`, `CHAT_MAX_REQUESTS_PER_DAY`) |
| `TTS_RATE_PER_MINUTE`, 40 | speak, per IP (one call per sentence) |
| `TTS_MAX_CHARS_PER_DAY`, 20000 | speak, all visitors per UTC day, counted on the cleaned text; failed calls are refunded |

## UI actions (allowlist)

The model decides which card accompanies an answer; the server validates it before the UI acts.
Actions can only open internal cards: no URLs, no navigation, no arbitrary ids, no HTML.

**Protocol** (one LLM call, works with streaming and any provider): prompt v5 tells the model to
start every reply with one line `ACTIONS: [...]` (a JSON array, possibly empty), a newline, then
the spoken answer. `backend/app/agents/actions.py` buffers the stream until that line is
complete and cuts it out, so it never reaches the visitor, TTS, History or the logs as text:

- The first non-blank text must start with `ACTIONS:` (case-insensitive; markdown `*`/backticks
  are stripped first). Anything else is decided at once as `[]` and streamed as answer text.
- The line ends at the first newline (text after the JSON on the same line is kept as answer).
  It may be at most 400 characters, and buffering stops 1.5 s after the first text arrives;
  either way the decision is `[]` and the rest of an unfinished `ACTIONS:` line is dropped,
  never shown. Malformed JSON → `[]`.
- Each item is validated with a strict Pydantic discriminated union (`extra="forbid"`, strict
  types, kebab-case ids). Unknown types, extra fields (`url`, `href`, …), unknown or draft
  `project_id`s and duplicates are dropped; at most 2 are kept. Rejections are logged by action
  type and reason only (`type=show_project reason=unknown_project`), never ids or visitor text.
- The result is sent as the single `action` event before any `token`, so the card opens while
  the answer is still being written and spoken. The frontend re-checks every action against the
  types and project ids it knows before opening a card.

| Action | Opens | Input |
|---|---|---|
| `show_project` | one project card | `project_id`: an approved project id (listed in the prompt) |
| `show_projects` | the project gallery | none |
| `show_skills` | technical skills | none |
| `show_experience` | practical training | none |
| `show_education` | education | none |
| `show_contact` | public contact options | none |

Two actions (e.g. two compared projects) open the first card; the panel offers the second
with a small "+1" switcher. `open_public_link` (approved `link_id`s from
`contact/public_links.md`) is planned, not enabled: the model cannot request it yet.

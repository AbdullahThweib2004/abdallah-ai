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
| Planned | `POST /api/v1/voice/transcribe` | Transcribe an uploaded visitor audio clip |
| Planned | `POST /api/v1/voice/generate` | Generate speech for validated response text |

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
prompt from `backend/app/agents/prompts/system_v3.md`, a small pinned identity context and those
chunks only. Cards are still chosen
by the frontend's temporary keyword stub, not by the model (that arrives with step 6).

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

## UI actions (allowlist)

The model can only request these actions. The backend rejects unknown action types and unknown
IDs. The frontend never runs arbitrary code or opens arbitrary URLs returned by the model.

| Action | Purpose | Required input |
|---|---|---|
| `show_projects` | Display the project gallery | Optional category filter |
| `show_project` | Open a specific project | Known `project_id` |
| `show_experience` | Display education and practical training | None |
| `show_skills` | Display technical skills | Optional category |
| `show_contact` | Display public contact options | None |
| `open_public_link` | Open an approved public link | Allowlisted `link_id` |

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
| Planned | `POST /api/v1/chat` | Submit a text turn and receive a structured response |
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

## `POST /api/v1/chat` (planned)

Request:

```json
{
  "session_id": "session_abc123",
  "message": "Can you explain the banking project?",
  "language": "en"
}
```

Response:

```json
{
  "session_id": "session_abc123",
  "response": "The banking platform combines ...",
  "language": "en",
  "action": { "type": "show_project", "project_id": "banking-intelligence" },
  "sources": ["banking_intelligence.md"]
}
```

Never expose private retrieval passages or internal prompts to the browser.

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

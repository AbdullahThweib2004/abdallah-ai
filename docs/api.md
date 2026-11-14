# API

Source: `docs/spec.pdf` §7.4, §13.

The API is versioned under `/api/v1`. All requests and responses use strict Pydantic models.
Interactive docs are served by FastAPI at `/docs` while the backend is running.

## Routes

| Status | Method / endpoint | Purpose |
|---|---|---|
| ✅ Implemented | `GET /api/v1/health` | Check service health |
| Planned | `POST /api/v1/sessions` | Create a conversation session |
| Planned | `POST /api/v1/chat` | Submit a text turn and receive a structured response |
| Planned | `POST /api/v1/voice/transcribe` | Transcribe an uploaded visitor audio clip |
| Planned | `POST /api/v1/voice/generate` | Generate speech for validated response text |
| Planned | `GET /api/v1/projects` | List public projects |
| Planned | `GET /api/v1/projects/{project_id}` | Get one public project |
| Planned | `GET /api/v1/profile` | Get public profile information |

Streaming routes may be added after the first prototype.

## `GET /api/v1/health`

```json
{ "status": "ok", "version": "0.1.0" }
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

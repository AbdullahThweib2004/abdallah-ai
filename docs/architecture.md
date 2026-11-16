# Architecture

Source: `docs/spec.pdf` §6, §12, §16.

## Principles

- **Modular by design.** The LLM, STT, TTS, avatar and RAG providers each sit behind an adapter
  interface, so you can replace one without redesigning the rest of the app.
- **The frontend never calls paid AI providers.** All secrets and orchestration logic stay in the
  FastAPI backend. The browser only talks to our own API.
- **Text first.** The site must stay usable in text mode if voice or avatar services fail.

## Request flow

```
VISITOR
  |
  v
NEXT.JS FRONTEND
  | text / microphone / playback / avatar UI
  v
FASTAPI APPLICATION BACKEND
  |
  +--> Session & Conversation Manager
  |
  +--> Speech-to-Text Adapter (voice input)
  |
  +--> AI Orchestrator
  |      |
  |      +--> RAG Retriever --> Knowledge Store
  |      |
  |      +--> LLM Provider Adapter
  |      |
  |      +--> Validated Portfolio Action
  |
  +--> Text-to-Speech Adapter
  |
  +--> Avatar Renderer / Avatar Provider
  |
  v
FRONTEND AUDIO + SYNCHRONIZED AVATAR + PROJECT UI
```

## Layers

| Layer | Stack | Responsibilities |
|---|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind | Layout, conversation controls, audio capture/playback, avatar display, project cards, responsive UI, RTL support |
| Backend | Python, FastAPI, Pydantic | Session handling, request validation, rate limits, orchestration, action allowlist, provider adapters |
| Knowledge | Markdown in `knowledge_base/` (source of truth), ChromaDB (vectors) | Approved, reviewed facts about Abdallah and his projects |
| Storage | SQLite (local dev), PostgreSQL later if needed | Sessions, project catalogue, approved links |

### Backend module map (`backend/app/`)

| Module | Purpose |
|---|---|
| `api/v1/` | Versioned HTTP routes |
| `core/` | Settings, versioning, shared infrastructure |
| `models/` | Pydantic request/response schemas |
| `agents/` | AI orchestrator, system prompt, action validation |
| `rag/` | Document loading, chunking, embeddings, retrieval |
| `voice/` | STT and TTS adapters |
| `avatar/` | Avatar provider adapters |
| `database/` | Persistence (SQLite → PostgreSQL) |

## Real-time communication

Start with request/response for text chat, then upload short audio clips for voice. Add streaming
(WebSocket for app events, and WebRTC or a managed service for two-way audio) only after the basic
flow works. WebSocket alone does not handle media transport, echo cancellation or network traversal.

## Data entities (planned)

| Entity | Key fields |
|---|---|
| Project | project_id, title, summary, technologies, repository_url, demo_url, status |
| Session | session_id, created_at, language, expires_at |
| Message | message_id, session_id, role, content, created_at (only if retention is enabled) |
| KnowledgeDocument | document_id, title, category, language, updated_at |
| ApprovedLink | link_id, label, url, visibility |

Data minimization: do not store raw audio, and store only what a session needs to run.

## Deployment topology (conceptual)

```
Public Internet
   |
   +--> Next.js frontend (e.g. Vercel or equivalent)
             |
             +--> FastAPI backend (Python hosting)
                       |
                       +--> LLM provider
                       +--> STT provider
                       +--> TTS provider
                       +--> Vector store / database
                       +--> Avatar service or GPU worker
```

Environments: **local** (mock adapters), **staging** (test credentials, sample knowledge) and
**production** (restricted secrets, rate limits, monitoring).

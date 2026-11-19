# Architecture

Source: the project specification (kept private), §6, §12, §16.

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

## Chat and retrieval (implemented, steps 4–5)

```
POST /api/v1/chat {message, history, ui_language}
  │
  ├─ rate limiter (per IP + global daily cap) ── over limit → 429
  ├─ language detection (share of Arabic-script words) → reply language
  ├─ Retriever (app/rag)                                   ~5 ms on CPU
  │    query = message (+ previous user message for follow-ups)
  │    Arabic → English expansion (glossary + generic vocabulary)
  │    ├─ vector search: paraphrase-multilingual-MiniLM-L12-v2 (int8 ONNX, onnxruntime)
  │    │    → precomputed index artifact (numpy dot product, cosine)
  │    ├─ BM25 keyword search (exact names: Nawa, MCP, FastAPI…)
  │    └─ Reciprocal Rank Fusion (ties share a rank) → top 6 → trim to 1,000 tokens
  ├─ prompt = system_v7 rules + pinned identity (≤300 tokens) + retrieved chunks
  │            each labeled [source: doc_id › heading]
  ├─ LLM adapter (Groq gpt-oss-120b, fallback 20b) → stream answer text only
  └─ SSE: start → token… → done {usage, latency_ms, sources} | error
```

- **Index**: one chunk per `##` section of each APPROVED document (sections over ~350 words
  are split with 50-word overlap), prefixed with "title — heading". Project/contact frontmatter
  becomes a "Project facts"/"Links" chunk. The glossary is not indexed (it drives query
  expansion) and UI copy such as the greeting is excluded.
- **Freshness**: the index artifact (`backend/.index/`: `vectors.npy` + `index.json` with ids,
  BM25 tokens and a hash of chunks + model + chunker version) is built at deploy time by
  `python -m app.deploy` (the Vercel build hook) and shipped inside the function. Startup
  rebuilds only when the hash changes (in memory on a read-only serverless filesystem).
- **Shared state**: on Vercel, rate limits, daily caps, the TTS character budget and the answer
  cache live in Upstash Redis (REST API), shared by all instances; locally they stay in memory.
- **Resilience**: if the embedding model cannot load, retrieval falls back to BM25 only; if
  the knowledge base fails to load, chat returns a friendly `unavailable` error.
- **Quality gates**: `evals/run_retrieval` (Recall@3/@6, MRR, EN/AR) and `evals/run_chat`
  (24+ behaviour cases, real provider).

## Layers

| Layer | Stack | Responsibilities |
|---|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind | Layout, conversation controls, audio capture/playback, avatar display, project cards, responsive UI, RTL support |
| Backend | Python, FastAPI, Pydantic | Session handling, request validation, rate limits, orchestration, action allowlist, provider adapters |
| Knowledge | Markdown in `knowledge_base/` (source of truth), a precomputed vector + BM25 index artifact (rebuilt from the Markdown at deploy time) | Approved, reviewed facts about Abdallah and his projects |
| Storage | Upstash Redis on Vercel (in memory locally) | Rate limits, daily caps, TTS budget, answer cache |

### Backend module map (`backend/app/`)

| Module | Purpose |
|---|---|
| `api/v1/` | Versioned HTTP routes |
| `core/` | Settings, versioning, shared infrastructure |
| `models/` | Pydantic request/response schemas |
| `agents/` | AI orchestrator, system prompt, action validation |
| `rag/` | Chunking, embeddings (onnxruntime), index artifact, hybrid retrieval, identity context |
| `llm/` | Provider adapters (OpenAI-compatible, Anthropic, fake) behind `LLMProvider` |
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

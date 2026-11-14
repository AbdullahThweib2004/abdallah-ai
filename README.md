# Abdullah AI – Interactive Voice Portfolio

> Don't just visit Abdullah's portfolio. Talk to Abdullah.

Abdullah AI is an interactive portfolio website. Visitors can talk, by text and later by voice,
with an AI-powered digital representative of Abdullah. The representative answers from a verified
knowledge base, speaks with an authorized voice, and appears as a realistic animated avatar. It is
clearly labelled as AI and never claims to be the real Abdullah.

The project is built in stages, starting on a small budget. **Current stage: 2 – Knowledge base**: content
templates for Abdullah to fill in, plus a strict validator. There are no AI features yet. See [`CLAUDE.md`](CLAUDE.md) for the full build
order and project rules, and [`docs/`](docs/) for the architecture, API and requirements.

## Repository layout

```
frontend/         Next.js (App Router, TypeScript, Tailwind)
backend/          FastAPI app (uv-managed, Python 3.12+)
knowledge_base/   Verified Markdown content about Abdullah (source of truth for RAG)
docs/             Specification, architecture, API and requirements
```

## Prerequisites

- Node.js 20.9+ and npm
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
cp .env.example .env                       # backend settings
cp .env.example frontend/.env.local        # frontend settings (only NEXT_PUBLIC_* values are used)
```

## Run the backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

- Health check: <http://localhost:8000/api/v1/health>
- API docs: <http://localhost:8000/docs>

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. When the backend is running, the badge shows **Backend online**.

## Tests and checks

```bash
cd backend
uv run pytest           # unit and API tests
uv run ruff check .     # lint
uv run python -m app.knowledge.cli validate   # knowledge base (see knowledge_base/README.md)

cd frontend
npm run lint
npm run build
```

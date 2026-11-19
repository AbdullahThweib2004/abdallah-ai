# Deploying Abdallah AI

Live: **https://abdallah-ai-three.vercel.app**

The whole site runs on Vercel's free Hobby plan as **one project with two services**
(`vercel.json`):

| Service | Root | What it serves |
|---|---|---|
| `backend` | `backend/` | FastAPI as one Python function. The public route `/api/v1/*` reaches it with the path unchanged. |
| `frontend` | `frontend/` | Next.js, which serves everything else. Server rendering reaches the backend through a service binding (`API_BASE_URL`). |

The browser calls the API on the same origin, so production needs no CORS.

Shared state lives in **Upstash Redis** (free plan, connected through the Vercel Marketplace as
`abdallah-ai-redis`): rate limits, daily caps, the TTS character budget and the answer cache.
Locally the same interfaces run in memory.

## Redeploy

- **Production**: push to `main`. The GitHub repository is connected to the Vercel project,
  so every push to `main` builds and deploys production.
- **Preview**: push any other branch or open a pull request. Previews are behind Vercel
  login (Deployment Protection), so `vercel curl <path> --deployment <url>` reaches them.
- **From your machine**: `npx vercel deploy` for a preview, `npx vercel deploy --prod` for
  production. `.vercelignore` keeps `.env`, `knowledge_base/_private/`, model caches and
  build outputs out of the upload.
- **Roll back**: `npx vercel rollback`, or promote an earlier deployment in the dashboard
  (Deployments, then the deployment's menu, then Promote to Production).

What a build does (see the Vercel build log):

1. `frontend`: `next build`.
2. `backend`: Vercel installs `backend/uv.lock`, then runs the build hook from
   `pyproject.toml` (`python -m app.deploy`):
   - copies `knowledge_base/` into the function, without `_private/`;
   - downloads the pinned embedding model (int8 ONNX, 118 MB);
   - builds the index artifact (`backend/.index/`: vectors, BM25 tokens and a content hash);
   - on production builds only, pre-warms the answer cache with the home page's suggestion
     chips in EN and AR. Already cached answers cost nothing, and a failed pre-warm never
     fails the build.

The function bundle is about 295 MB (the limit is 500 MB).

## Update the knowledge base

1. Edit the Markdown in `knowledge_base/` (see `knowledge_base/README.md`).
2. Check it locally:
   - `cd backend && uv run python -m app.knowledge.cli validate`
   - `uv run python -m evals.run_retrieval`: keep Recall@6 at 1.0 in EN and AR.
3. Commit and push to `main`.

Vercel rebuilds the index in the build step. The answer cache is keyed by a hash of the
approved knowledge and the prompt version, so old answers are never served again (they
expire from Redis after 30 days). The production build pre-warms the new answers.

Changing the prompt works the same way: add `backend/app/agents/prompts/system_vN.md`, bump
`PROMPT_VERSION`, run the evals, then push.

## Environment variables

Set them in Vercel (Project, then Settings, then Environment Variables) or with
`npx vercel env add NAME --environment production,preview`. Never put them in the repository.
Changes apply to the **next** deployment, so redeploy afterwards.

| Variable | Value / note |
|---|---|
| `APP_ENV` | `production`: production per-IP limits, API docs hidden |
| `CORS_ORIGINS` | `https://abdallah-ai-three.vercel.app` (same-origin calls don't need it, other sites are refused) |
| `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_FALLBACK_MODEL`, `LLM_REASONING_EFFORT` | Groq `openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b` |
| `LLM_API_KEY` | Groq key (**Secret**). Also used for Whisper. |
| `STT_PROVIDER`, `STT_MODEL` | `groq`, `whisper-large-v3` |
| `TTS_PROVIDER`, `TTS_MODEL`, `TTS_VOICE_EN`, `TTS_VOICE_AR` | ElevenLabs, stock voice |
| `ELEVENLABS_API_KEY` | **Secret** |
| `CHAT_MAX_REQUESTS_PER_DAY` | global daily cap for chat and voice questions (500) |
| `TTS_MAX_CHARS_PER_DAY` | global daily ElevenLabs character budget (20,000) |
| `KV_REST_API_URL`, `KV_REST_API_TOKEN` | set by the Upstash integration; don't edit by hand |
| `LLM_INPUT_COST_PER_MTOK`, `LLM_OUTPUT_COST_PER_MTOK` | only for cost estimates in logs and evals |

Vercel sets `VERCEL`, `VERCEL_ENV` and `VERCEL_PROJECT_PRODUCTION_URL` automatically. The
backend uses them to trust Vercel's client-IP headers, to keep preview counters apart from
production, and to build the site URL.

## Rotate keys

1. **Groq**: create a new key in the Groq console, then:
   `printf %s "$NEW_KEY" | npx vercel env add LLM_API_KEY --environment production,preview --sensitive --force`.
   Redeploy (`npx vercel deploy --prod`, or push), check that a question gets answered, then
   delete the old key in Groq. Update your local `.env` too.
2. **ElevenLabs**: the same steps with `ELEVENLABS_API_KEY`. If the key fails, the site keeps
   talking with the browser's own voice.
3. **Upstash**: rotate the token in the Upstash console (or the Vercel Storage tab, under
   the database's settings), make sure `KV_REST_API_TOKEN` in the project shows the new value,
   then redeploy. While Redis is unreachable, each instance falls back to in-memory limits and
   logs it.

## Usage and costs

Cost guards built into the app:

| Guard | Default |
|---|---|
| Per IP | 8 chat messages per minute and 60 per day; 6 voice questions per minute |
| Global | `CHAT_MAX_REQUESTS_PER_DAY` = 500, shared by all instances through Redis |
| ElevenLabs | `TTS_MAX_CHARS_PER_DAY` = 20,000 characters (UTC day); over it, the browser voice speaks |
| Answer cache | Repeated first questions, and their audio, cost no tokens and no characters |

Provider dashboards and limits:

| Service | Where to check | Notes |
|---|---|---|
| **Groq** | Groq console, Usage | A **spend limit of 3 USD/month** is set in the Groq console's billing settings. When it is reached, Groq refuses requests and visitors see "Busy right now, try again in N seconds" (the site never spends more). Developer tier: 250K tokens/min and 500K requests/day per model. About $0.00034 per question. |
| **ElevenLabs** | ElevenLabs account, Usage | Capped by our own daily character budget. |
| **Vercel** | Project, then Usage | The free Hobby allotment is 1M function invocations, 4 h Active CPU and 360 GB-hrs memory per month. Waiting for Groq or ElevenLabs is I/O and doesn't count as Active CPU. |
| **Upstash** | Vercel Storage tab, or the Upstash console | The free plan has a monthly command allowance. The site uses about 1 command per rate check and 1–3 per chat (cache), so about 3–5 per question. |

Logs: `npx vercel logs --deployment https://abdallah-ai-three.vercel.app`. Hobby keeps
runtime logs for 1 hour. Every 429 is one `rate_limit source=… limit=…` line, and logs never
contain visitor messages, transcripts or IP addresses.

## Check a deployment

```bash
cd backend
# Evals against the deployed API: real routing, cache and limits. Mind the per-IP limit.
uv run python -m evals.run_chat    --api-url https://abdallah-ai-three.vercel.app --limit 6 --delay 8
uv run python -m evals.run_actions --api-url https://abdallah-ai-three.vercel.app --limit 6 --delay 8

# Try a lower limit on a PREVIEW only (an environment override for that one deployment):
npx vercel deploy -e CHAT_RATE_PER_MINUTE=2
npx vercel curl /api/v1/chat --deployment <preview-url> -- -X POST \
  -H 'content-type: application/json' -d '{"message":"Hi"}' -i   # the 3rd within a minute gets 429
```

## Measurements (2026-11-19, production)

| Measurement | Result |
|---|---|
| Typed question → first answer text, in the browser | 2.3 s (EN), 2.8 s (AR), including the model loading on a fresh instance |
| Cold API request (no page load first) | full answer 3.8 s |
| Warm API request | first byte 0.5 s, full answer 1.1 s |
| Voice, end of speech → first audio (headless Chrome, fake microphone, from Europe) | 6.2 s (EN), 5.7 s (AR) |
| Voice server steps | Whisper 0.26–0.33 s, LLM 0.4–0.7 s, ElevenLabs first byte 0.17–0.38 s |
| Function startup | 1.3 s; the embedding model loads in the background while the first request runs |
| Retrieval | ~5 ms once warm |

The rest of the voice time is the 1.5 s silence wait and three round trips to US-East.

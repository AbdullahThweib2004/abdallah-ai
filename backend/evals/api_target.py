"""Evaluate a DEPLOYED backend over HTTP instead of calling the provider directly:

    uv run python -m evals.run_chat --api-url https://<site> --only ... --delay 8

Each case is sent to `<api-url>/api/v1/chat` exactly as the browser sends it; the SSE stream
gives the answer tokens, the validated `action` event and the usage. The reply is rebuilt as
"ACTIONS: [...]\\n<answer>" so the normal grading applies. A 429 (our per-IP limit) or a
`busy` error (provider limits) becomes an `LLMRateLimitError`, so the quota guard waits or
stops as usual. Answers served from the production answer cache are counted (`cached`).
Mind the site's per-IP limit (8 requests/minute): use `--delay 8`.
"""

import json

import httpx

from app.llm.base import LLMRateLimitError, Usage
from app.models.chat import ChatTurn


class ApiTarget:
    name = "deployed-api"
    tracker = None

    def __init__(
        self,
        base_url: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = f"{self.base_url}/api/v1/chat"
        self.cached = 0
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def ask(self, case: dict) -> tuple[str, Usage]:
        payload = {
            "message": case["message"],
            "history": [ChatTurn(**turn).model_dump() for turn in case.get("history", [])],
            "ui_language": case.get("language", "en"),
        }
        actions: list[dict] = []
        parts: list[str] = []
        usage = Usage()
        async with self._client.stream("POST", self.model, json=payload) as response:
            if response.status_code == 429:
                retry = float(response.headers.get("retry-after", "60"))
                raise LLMRateLimitError("site rate limit (429)", retry, "app")
            response.raise_for_status()
            event = ""
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    if event == "action":
                        actions = data.get("actions", [])
                    elif event == "token":
                        parts.append(data.get("text", ""))
                    elif event == "done":
                        usage = Usage(**data.get("usage", {}))
                        self.cached += bool(data.get("cached"))
                    elif event == "error":
                        if data.get("code") == "busy":
                            raise LLMRateLimitError("busy", data.get("retry_after"), "busy")
                        raise RuntimeError(f"API error: {data.get('code')}")
        prefix = f"ACTIONS: {json.dumps(actions, ensure_ascii=False)}\n"
        return prefix + "".join(parts), usage

    async def aclose(self) -> None:
        await self._client.aclose()

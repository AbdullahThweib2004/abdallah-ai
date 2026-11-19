"""Minimal async client for Upstash Redis over its REST API (no extra dependency: httpx).

Serverless functions have no long-lived TCP connections, so Upstash's HTTPS API is used:
`POST /` with a JSON command array, `POST /pipeline` with a list of them. Values are strings;
binary data (audio) is stored base64-encoded by the caller. Errors raise `RedisError`; callers
decide whether to fail open (cache) or closed (limits).
"""

import logging
from collections.abc import Sequence
from typing import Any

import httpx

logger = logging.getLogger(__name__)

Command = Sequence[str | int | float]


class RedisError(Exception):
    pass


class UpstashRedis:
    def __init__(
        self,
        url: str,
        token: str,
        *,
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    async def _post(self, path: str, payload: Any) -> Any:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise RedisError(f"redis request failed: {type(exc).__name__}") from None
        if response.status_code != 200:
            raise RedisError(f"redis returned HTTP {response.status_code}")
        return response.json()

    async def execute(self, *command: str | int | float) -> Any:
        data = await self._post("/", [str(part) for part in command])
        if "error" in data:
            raise RedisError(f"redis error: {data['error']}")
        return data.get("result")

    async def pipeline(self, commands: Sequence[Command]) -> list[Any]:
        if not commands:
            return []
        data = await self._post("/pipeline", [[str(p) for p in c] for c in commands])
        results = []
        for item in data:
            if "error" in item:
                raise RedisError(f"redis error: {item['error']}")
            results.append(item.get("result"))
        return results

    async def eval(self, script: str, keys: Sequence[str], args: Sequence[str | int]) -> Any:
        return await self.execute("EVAL", script, len(keys), *keys, *args)

    async def aclose(self) -> None:
        await self._client.aclose()

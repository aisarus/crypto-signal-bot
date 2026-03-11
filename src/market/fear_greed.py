from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger(__name__)

FNG_URL = "https://api.alternative.me/fng/"


class FearGreedIndex:
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._cache: int | None = None
        self._cache_ts: float = 0
        self._cache_ttl: float = 30 * 60  # 30 min

    def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _fetch(self, limit: int = 1) -> list[dict]:
        try:
            async with self._sess().get(FNG_URL, params={"limit": limit}) as r:
                r.raise_for_status()
                data = await r.json(content_type=None)
                return data.get("data", [])
        except Exception as e:
            log.warning("FearGreed fetch error: %s", e)
            return []

    async def get_current(self) -> int | None:
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_ts) < self._cache_ttl:
            return self._cache
        return await self.refresh()

    async def refresh(self) -> int | None:
        rows = await self._fetch(1)
        if rows:
            val = int(rows[0]["value"])
            self._cache = val
            self._cache_ts = time.monotonic()
            return val
        return None

    async def get_history(self, days: int) -> list[tuple[datetime, int]]:
        rows = await self._fetch(days)
        result = []
        for r in rows:
            ts = datetime.fromtimestamp(int(r["timestamp"]), tz=timezone.utc)
            result.append((ts, int(r["value"])))
        return sorted(result, key=lambda x: x[0])

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

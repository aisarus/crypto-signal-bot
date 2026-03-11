from __future__ import annotations
import asyncio
import logging
import time

import aiohttp

log = logging.getLogger(__name__)

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._session: aiohttp.ClientSession | None = None
        self._request_times: list[float] = []
        self._rpm_limit = 14  # stay under 15 RPM

    def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _rate_limit(self) -> None:
        now = time.monotonic()
        # Keep only last 60s
        self._request_times = [t for t in self._request_times if now - t < 60]
        if len(self._request_times) >= self._rpm_limit:
            wait = 60 - (now - self._request_times[0]) + 0.1
            if wait > 0:
                log.debug("Gemini rate limit: sleeping %.1fs", wait)
                await asyncio.sleep(wait)
        self._request_times.append(time.monotonic())

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str | None:
        if not self.api_key:
            return None
        url = _GEMINI_URL.format(model=self.model, key=self.api_key)
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        for attempt in range(2):
            try:
                await self._rate_limit()
                async with self._sess().post(url, json=body) as r:
                    if r.status == 429:
                        await asyncio.sleep(5)
                        continue
                    r.raise_for_status()
                    data = await r.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return text.strip()
            except Exception as e:
                log.warning("Gemini attempt %d failed: %s", attempt + 1, e)
                if attempt == 0:
                    await asyncio.sleep(2)
        return None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

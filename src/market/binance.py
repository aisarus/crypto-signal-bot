from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger(__name__)

BASE = "https://api.binance.com"


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TickerStats:
    volume: float
    quote_volume: float
    price_change_pct: float
    high_24h: float
    low_24h: float


class BinanceClient:
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None

    def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _get(self, url: str, params: dict | None = None, retries: int = 3) -> dict | list:
        delay = 1.0
        for attempt in range(retries):
            try:
                async with self._sess().get(url, params=params) as r:
                    r.raise_for_status()
                    return await r.json()
            except Exception as e:
                if attempt == retries - 1:
                    raise
                log.warning("Binance retry %d/%d: %s", attempt + 1, retries, e)
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")

    async def get_all_prices(self, symbols: list[str]) -> dict[str, float]:
        data = await self._get(f"{BASE}/api/v3/ticker/price")
        return {d["symbol"]: float(d["price"]) for d in data if d["symbol"] in symbols}

    async def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        data = await self._get(
            f"{BASE}/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        return [
            Candle(
                timestamp=datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
            )
            for k in data
        ]

    async def get_24h_stats(self, symbol: str) -> TickerStats:
        data = await self._get(f"{BASE}/api/v3/ticker/24hr", {"symbol": symbol})
        return TickerStats(
            volume=float(data["volume"]),
            quote_volume=float(data["quoteVolume"]),
            price_change_pct=float(data["priceChangePercent"]),
            high_24h=float(data["highPrice"]),
            low_24h=float(data["lowPrice"]),
        )

    async def ping(self) -> float:
        """Returns latency in ms or raises."""
        import time
        t0 = time.monotonic()
        await self._get(f"{BASE}/api/v3/ping")
        return (time.monotonic() - t0) * 1000

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

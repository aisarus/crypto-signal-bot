from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone

import aiohttp

from src.market.binance import Candle, TickerStats

log = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"

SYMBOL_MAP: dict[str, str] = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple",
    "DOGEUSDT": "dogecoin",
    "ADAUSDT": "cardano",
    "AVAXUSDT": "avalanche-2",
    "DOTUSDT": "polkadot",
    "MATICUSDT": "matic-network",
}


class CoinGeckoClient:
    """Бесплатный API, работает из любого региона без ключей. ~30 req/min."""

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._last_request_times: list[float] = []
        self._rpm_limit = 28  # stay safely under 30

    def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Accept": "application/json"},
            )
        return self._session

    async def _rate_limit(self) -> None:
        now = time.monotonic()
        self._last_request_times = [t for t in self._last_request_times if now - t < 60]
        if len(self._last_request_times) >= self._rpm_limit:
            wait = 60 - (now - self._last_request_times[0]) + 0.5
            if wait > 0:
                log.debug("CoinGecko rate limit: sleeping %.1fs", wait)
                await asyncio.sleep(wait)
        self._last_request_times.append(time.monotonic())

    async def _get(self, path: str, params: dict | None = None, retries: int = 3) -> dict | list:
        url = f"{BASE_URL}{path}"
        delay = 2.0
        for attempt in range(retries):
            try:
                await self._rate_limit()
                async with self._sess().get(url, params=params) as r:
                    if r.status == 429:
                        log.warning("CoinGecko 429 rate limit, sleeping 60s")
                        await asyncio.sleep(60)
                        continue
                    r.raise_for_status()
                    return await r.json(content_type=None)
            except Exception as e:
                if attempt == retries - 1:
                    raise
                log.warning("CoinGecko retry %d/%d: %s", attempt + 1, retries, e)
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError("CoinGecko: all retries failed")

    def _coin_id(self, symbol: str) -> str | None:
        return SYMBOL_MAP.get(symbol.upper())

    async def get_all_prices(self, symbols: list[str]) -> dict[str, float]:
        ids = [self._coin_id(s) for s in symbols if self._coin_id(s)]
        if not ids:
            return {}
        data = await self._get(
            "/simple/price",
            {"ids": ",".join(ids), "vs_currencies": "usd"},
        )
        # Reverse map: coin_id → symbol
        rev = {v: k for k, v in SYMBOL_MAP.items() if k in symbols}
        return {rev[cid]: float(info["usd"]) for cid, info in data.items() if cid in rev}

    async def get_ohlc(self, symbol: str, days: int = 200) -> list[Candle]:
        """
        Fetch price history as synthetic daily candles via /market_chart.
        CoinGecko auto-granularity: days > 90 → daily data.
        For hourly (days≤3) returns ~hourly data.
        """
        coin_id = self._coin_id(symbol)
        if not coin_id:
            log.warning("CoinGecko: unknown symbol %s", symbol)
            return []

        cg_days = max(days, 91) if days > 7 else days  # force daily for large requests
        data = await self._get(
            f"/coins/{coin_id}/market_chart",
            {"vs_currency": "usd", "days": str(cg_days)},
        )
        prices = data.get("prices", [])
        volumes = data.get("total_volumes", [])
        vol_map = {int(v[0]): v[1] for v in volumes}

        candles: list[Candle] = []
        for ts_ms, price in prices:
            vol = vol_map.get(int(ts_ms), 0.0)
            candles.append(Candle(
                timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                open=float(price),
                high=float(price),
                low=float(price),
                close=float(price),
                volume=float(vol),
            ))
        candles.sort(key=lambda c: c.timestamp)
        return candles[-days:]

    async def get_market_data(self, symbol: str) -> TickerStats | None:
        coin_id = self._coin_id(symbol)
        if not coin_id:
            return None
        data = await self._get(
            f"/coins/{coin_id}",
            {"localization": "false", "tickers": "false",
             "community_data": "false", "developer_data": "false"},
        )
        mkt = data.get("market_data", {})
        return TickerStats(
            volume=float(mkt.get("total_volume", {}).get("usd", 0)),
            quote_volume=float(mkt.get("total_volume", {}).get("usd", 0)),
            price_change_pct=float(mkt.get("price_change_percentage_24h") or 0),
            high_24h=float(mkt.get("high_24h", {}).get("usd", 0)),
            low_24h=float(mkt.get("low_24h", {}).get("usd", 0)),
        )

    async def ping(self) -> float:
        import time as _time
        t0 = _time.monotonic()
        await self._get("/ping")
        return (_time.monotonic() - t0) * 1000

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

from __future__ import annotations
import asyncio
import logging
from datetime import datetime

import aiohttp

from src.market.binance import BinanceClient, Candle
from src.market.fear_greed import FearGreedIndex

log = logging.getLogger(__name__)


class HistoricalLoader:
    def __init__(self, binance: BinanceClient, fg: FearGreedIndex):
        self.binance = binance
        self.fg = fg

    async def load_candles(self, symbol: str, interval: str, days: int) -> list[Candle]:
        """Load candles in batches of 1000 with 200ms pause between batches."""
        all_candles: list[Candle] = []
        batch_size = 1000
        total_needed = days if interval == "1d" else days * 24

        batches = (total_needed + batch_size - 1) // batch_size
        for i in range(batches):
            limit = min(batch_size, total_needed - len(all_candles))
            if limit <= 0:
                break
            try:
                batch = await self.binance.get_klines(symbol, interval, limit)
                all_candles.extend(batch)
                if i < batches - 1:
                    await asyncio.sleep(0.2)
            except Exception as e:
                log.warning("Failed to load batch %d for %s %s: %s", i, symbol, interval, e)
                break

        # Deduplicate and sort
        seen = set()
        unique = []
        for c in all_candles:
            if c.timestamp not in seen:
                seen.add(c.timestamp)
                unique.append(c)
        unique.sort(key=lambda c: c.timestamp)
        return unique[-days:]

    async def load_fear_greed(self, days: int) -> list[tuple[datetime, int]]:
        return await self.fg.get_history(days)

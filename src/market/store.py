from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiosqlite

log = logging.getLogger(__name__)


class MarketStore:
    def __init__(self, db_path: str = "data/signals.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
        return self._db

    async def init_db(self) -> None:
        import os
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        db = await self._conn()
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_prices_sym_ts ON prices (symbol, timestamp);

            CREATE TABLE IF NOT EXISTS candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                ts TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                UNIQUE(symbol, interval, ts)
            );
            CREATE INDEX IF NOT EXISTS idx_candles_sym_int_ts ON candles (symbol, interval, ts);

            CREATE TABLE IF NOT EXISTS signals_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                signal_type TEXT,
                score REAL,
                timestamp TEXT
            );

            CREATE TABLE IF NOT EXISTS backtest_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                days INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                summary TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(symbol, days)
            );
        """)
        await db.commit()
        log.info("Database initialised at %s", self.db_path)

    async def save_price(self, symbol: str, price: float, volume: float, ts: datetime) -> None:
        db = await self._conn()
        await db.execute(
            "INSERT INTO prices (symbol, price, volume, timestamp) VALUES (?, ?, ?, ?)",
            (symbol, price, volume, ts.isoformat()),
        )
        await db.commit()

    async def save_candles(self, symbol: str, interval: str, candles: list) -> None:
        if not candles:
            return
        db = await self._conn()
        async with self._lock:
            await db.executemany(
                """INSERT OR REPLACE INTO candles (symbol, interval, ts, open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (symbol, interval, c.timestamp.isoformat(), c.open, c.high, c.low, c.close, c.volume)
                    for c in candles
                ],
            )
            await db.commit()

    async def get_hourly_closes(self, symbol: str, count: int) -> list[float]:
        db = await self._conn()
        async with db.execute(
            "SELECT close FROM candles WHERE symbol=? AND interval='1h' ORDER BY ts DESC LIMIT ?",
            (symbol, count),
        ) as cur:
            rows = await cur.fetchall()
        return [r[0] for r in reversed(rows)]

    async def get_daily_closes(self, symbol: str, days: int) -> list[float]:
        db = await self._conn()
        async with db.execute(
            "SELECT close FROM candles WHERE symbol=? AND interval='1d' ORDER BY ts DESC LIMIT ?",
            (symbol, days),
        ) as cur:
            rows = await cur.fetchall()
        return [r[0] for r in reversed(rows)]

    async def get_daily_volumes(self, symbol: str, days: int) -> list[float]:
        db = await self._conn()
        async with db.execute(
            "SELECT volume FROM candles WHERE symbol=? AND interval='1d' ORDER BY ts DESC LIMIT ?",
            (symbol, days),
        ) as cur:
            rows = await cur.fetchall()
        return [r[0] for r in reversed(rows)]

    async def get_latest_price(self, symbol: str) -> float | None:
        db = await self._conn()
        async with db.execute(
            "SELECT price FROM prices WHERE symbol=? ORDER BY timestamp DESC LIMIT 1",
            (symbol,),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def get_record_count(self) -> int:
        db = await self._conn()
        async with db.execute("SELECT COUNT(*) FROM prices") as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def save_signal_log(self, symbol: str, signal_type: str, score: float, ts: datetime) -> None:
        db = await self._conn()
        await db.execute(
            "INSERT INTO signals_log (symbol, signal_type, score, timestamp) VALUES (?, ?, ?, ?)",
            (symbol, signal_type, score, ts.isoformat()),
        )
        await db.commit()

    async def get_signal_count(self, hours: int = 24) -> int:
        db = await self._conn()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM signals_log WHERE timestamp > ?", (since,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def save_backtest_cache(self, symbol: str, days: int, result_json: str, summary: str) -> None:
        db = await self._conn()
        await db.execute(
            """INSERT OR REPLACE INTO backtest_cache (symbol, days, result_json, summary, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (symbol, days, result_json, summary, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()

    async def get_backtest_cache(self, symbol: str, days: int, max_age_hours: int = 24) -> str | None:
        db = await self._conn()
        since = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        async with db.execute(
            "SELECT summary FROM backtest_cache WHERE symbol=? AND days=? AND updated_at > ?",
            (symbol, days, since),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def cleanup(self, keep_days: int = 90) -> None:
        db = await self._conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
        await db.execute("DELETE FROM prices WHERE timestamp < ?", (cutoff,))
        await db.commit()
        log.debug("Cleanup done, cutoff=%s", cutoff)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

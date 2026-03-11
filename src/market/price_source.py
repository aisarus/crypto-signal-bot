from __future__ import annotations
import logging

from src.market.binance import BinanceClient, Candle, TickerStats
from src.market.coingecko import CoinGeckoClient, SYMBOL_MAP

log = logging.getLogger(__name__)


class PriceSource:
    """
    Единый источник данных. Пробует Binance сначала, при ошибке 451/любой —
    переключается на CoinGecko. Оба клиента имеют одинаковый интерфейс.
    """

    def __init__(self, binance: BinanceClient, coingecko: CoinGeckoClient):
        self.binance = binance
        self.coingecko = coingecko
        self.use_binance = True
        self._source_name = "Binance"

    async def init(self) -> None:
        """Проверить доступность Binance при старте."""
        self.use_binance = await self.binance.is_available()
        self._source_name = "Binance" if self.use_binance else "CoinGecko"
        log.info("Источник данных: %s", self._source_name)

    @property
    def source_name(self) -> str:
        return self._source_name

    def _on_binance_fail(self, exc: Exception) -> None:
        log.warning("Binance недоступен (%s), переключаюсь на CoinGecko", exc)
        self.use_binance = False
        self._source_name = "CoinGecko"

    async def get_all_prices(self, symbols: list[str]) -> dict[str, float]:
        if self.use_binance:
            try:
                return await self.binance.get_all_prices(symbols)
            except Exception as e:
                self._on_binance_fail(e)
        return await self.coingecko.get_all_prices(symbols)

    async def get_klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        if self.use_binance:
            try:
                return await self.binance.get_klines(symbol, interval, limit)
            except Exception as e:
                self._on_binance_fail(e)
        # CoinGecko: map interval → days
        days = limit if interval == "1d" else 3
        return await self.coingecko.get_ohlc(symbol, days=days)

    async def get_24h_stats(self, symbol: str) -> TickerStats | None:
        if self.use_binance:
            try:
                return await self.binance.get_24h_stats(symbol)
            except Exception as e:
                self._on_binance_fail(e)
        return await self.coingecko.get_market_data(symbol)

    async def ping(self) -> tuple[str, float | None]:
        """Returns (source_name, latency_ms_or_None)."""
        if self.use_binance:
            try:
                ms = await self.binance.ping()
                return ("Binance", ms)
            except Exception:
                pass
        try:
            ms = await self.coingecko.ping()
            return ("CoinGecko", ms)
        except Exception:
            return (self._source_name, None)

    def supports_symbol(self, symbol: str) -> bool:
        """Check if symbol is supported (needed for CoinGecko mode)."""
        if self.use_binance:
            return True  # Binance supports any symbol
        return symbol.upper() in SYMBOL_MAP

    async def close(self) -> None:
        await self.binance.close()
        await self.coingecko.close()

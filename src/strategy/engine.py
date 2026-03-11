from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from src.market.indicators import Indicators
from src.strategy.scorer import MarketSnapshot, ScoreBreakdown, Scorer

log = logging.getLogger(__name__)


class SignalType(Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

    def is_actionable(self) -> bool:
        return self != SignalType.NEUTRAL

    def is_bullish(self) -> bool:
        return self in (SignalType.BUY, SignalType.STRONG_BUY)

    def is_bearish(self) -> bool:
        return self in (SignalType.SELL, SignalType.STRONG_SELL)


def score_to_signal(score: float) -> SignalType:
    if score >= 0.6:
        return SignalType.STRONG_BUY
    elif score >= 0.3:
        return SignalType.BUY
    elif score <= -0.6:
        return SignalType.STRONG_SELL
    elif score <= -0.3:
        return SignalType.SELL
    return SignalType.NEUTRAL


@dataclass
class Signal:
    type: SignalType
    symbol: str
    price: float
    breakdown: ScoreBreakdown
    backtest_summary: str | None
    ai_comment: str | None
    timestamp: datetime


class StrategyEngine:
    def __init__(self, scorer: Scorer, store, price_source, fear_greed, indicators: Indicators):
        self.scorer = scorer
        self.store = store
        self.price_source = price_source
        self.fear_greed = fear_greed
        self.indicators = indicators

    async def build_snapshot(self, symbol: str) -> MarketSnapshot:
        # Price
        price = await self.store.get_latest_price(symbol)
        if price is None:
            try:
                prices = await self.price_source.get_all_prices([symbol])
                price = prices.get(symbol, 0.0)
            except Exception as e:
                log.warning("Cannot get price for %s: %s", symbol, e)
                price = 0.0

        # Historical data
        daily_closes = await self.store.get_daily_closes(symbol, 220)
        hourly_closes = await self.store.get_hourly_closes(symbol, 50)
        daily_volumes = await self.store.get_daily_volumes(symbol, 25)

        closes_for_rsi = hourly_closes if len(hourly_closes) >= 15 else daily_closes
        rsi = self.indicators.rsi(closes_for_rsi, 14)
        sma_200 = self.indicators.sma(daily_closes, 200)
        ema_50 = self.indicators.ema(daily_closes, 50)

        vol_list = daily_volumes if daily_volumes else []
        volume_ratio = self.indicators.volume_ratio(vol_list, 20) if len(vol_list) > 20 else None

        # Fear & Greed
        try:
            fg = await self.fear_greed.get_current()
        except Exception:
            fg = None

        # 24h change
        change_24h = None
        try:
            stats = await self.price_source.get_24h_stats(symbol)
            change_24h = stats.price_change_pct
        except Exception:
            pass

        return MarketSnapshot(
            symbol=symbol,
            price=price,
            rsi=rsi,
            sma_200=sma_200,
            ema_50=ema_50,
            fear_greed=fg,
            volume_ratio=volume_ratio,
            change_24h_pct=change_24h,
            timestamp=datetime.now(timezone.utc),
        )

    async def evaluate(self, symbol: str) -> Signal:
        snap = await self.build_snapshot(symbol)
        breakdown = self.scorer.score(snap)
        signal_type = score_to_signal(breakdown.total_score)

        backtest_summary = await self.store.get_backtest_cache(symbol, 365)

        return Signal(
            type=signal_type,
            symbol=symbol,
            price=snap.price,
            breakdown=breakdown,
            backtest_summary=backtest_summary,
            ai_comment=None,
            timestamp=snap.timestamp,
        )

    async def evaluate_all(self) -> list[Signal]:
        from src.config import load_config
        cfg = load_config()
        signals = []
        for symbol in cfg.coins:
            try:
                sig = await self.evaluate(symbol)
                signals.append(sig)
            except Exception as e:
                log.error("Error evaluating %s: %s", symbol, e)
        return signals

    async def force_check(self, symbol: str | None = None, coins: list[str] | None = None) -> list[Signal]:
        """Force check with fresh data. Ignores cooldown (caller handles that)."""
        targets = [symbol] if symbol else (coins or [])
        signals = []
        for sym in targets:
            try:
                # Refresh data first
                candles_1d = await self.price_source.get_klines(sym, "1d", 200)
                await self.store.save_candles(sym, "1d", candles_1d)
                candles_1h = await self.price_source.get_klines(sym, "1h", 50)
                await self.store.save_candles(sym, "1h", candles_1h)
                await self.fear_greed.refresh()

                sig = await self.evaluate(sym)
                signals.append(sig)
            except Exception as e:
                log.error("force_check error for %s: %s", sym, e)
        return signals

from __future__ import annotations
import logging

log = logging.getLogger(__name__)


class Indicators:
    @staticmethod
    def rsi(closes: list[float], period: int = 14) -> float | None:
        if len(closes) < period + 1:
            return None
        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i - 1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))

        # Wilder's smoothing
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    @staticmethod
    def sma(closes: list[float], period: int = 200) -> float | None:
        if len(closes) < period:
            return None
        return sum(closes[-period:]) / period

    @staticmethod
    def ema(closes: list[float], period: int = 50) -> float | None:
        if len(closes) < period:
            return None
        k = 2 / (period + 1)
        ema_val = sum(closes[:period]) / period
        for price in closes[period:]:
            ema_val = price * k + ema_val * (1 - k)
        return round(ema_val, 2)

    @staticmethod
    def volume_ratio(volumes: list[float], period: int = 20) -> float | None:
        if len(volumes) < period + 1:
            return None
        avg = sum(volumes[-period - 1 : -1]) / period
        if avg == 0:
            return None
        return round(volumes[-1] / avg, 3)

    @staticmethod
    def crossed_sma(closes: list[float], sma: float, lookback: int = 5) -> str | None:
        if len(closes) < lookback + 1:
            return None
        recent = closes[-lookback:]
        prev = closes[-lookback - 1]
        current = closes[-1]
        # Check if crossed up: was below, now above
        if prev < sma and current > sma:
            return "up"
        # Check if crossed down: was above, now below
        if prev > sma and current < sma:
            return "down"
        return None

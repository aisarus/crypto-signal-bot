from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime

from src.config import StrategyParams

log = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    symbol: str
    price: float
    rsi: float | None
    sma_200: float | None
    ema_50: float | None
    fear_greed: int | None
    volume_ratio: float | None
    change_24h_pct: float | None
    timestamp: datetime


@dataclass
class ScoreBreakdown:
    rsi_score: float
    rsi_value: float | None
    rsi_label: str
    rsi_hit: bool

    fg_score: float
    fg_value: int | None
    fg_label: str
    fg_hit: bool

    sma_score: float
    sma_value: float | None
    sma_label: str
    sma_hit: bool

    vol_score: float
    vol_ratio: float | None
    vol_label: str
    vol_hit: bool

    total_score: float
    hits: int
    confidence_bar: str


def _confidence_bar(score: float) -> str:
    filled = round(abs(score) * 10)
    filled = max(0, min(10, filled))
    return "█" * filled + "░" * (10 - filled)


class Scorer:
    def __init__(self, params: StrategyParams):
        self.p = params

    def score(self, snap: MarketSnapshot) -> ScoreBreakdown:
        p = self.p

        # --- RSI ---
        rsi = snap.rsi
        if rsi is None:
            rsi_score, rsi_label, rsi_hit = 0.0, "нет данных", False
        elif rsi <= 20:
            rsi_score, rsi_label, rsi_hit = 1.0, "экстремально перепродан", True
        elif rsi <= p.rsi_oversold:
            rsi_score, rsi_label, rsi_hit = 0.5, "перепродан", True
        elif rsi >= 80:
            rsi_score, rsi_label, rsi_hit = -1.0, "экстремально перекуплен", True
        elif rsi >= p.rsi_overbought:
            rsi_score, rsi_label, rsi_hit = -0.5, "перекуплен", True
        else:
            rsi_score, rsi_label, rsi_hit = 0.0, "нейтрально", False

        # --- Fear & Greed (contrarian) ---
        fg = snap.fear_greed
        if fg is None:
            fg_score, fg_label, fg_hit = 0.0, "нет данных", False
        elif fg <= 15:
            fg_score, fg_label, fg_hit = 1.0, "экстремальный страх", True
        elif fg <= p.fg_fear:
            fg_score, fg_label, fg_hit = 0.5, "страх", True
        elif fg >= 85:
            fg_score, fg_label, fg_hit = -1.0, "эйфория", True
        elif fg >= p.fg_greed:
            fg_score, fg_label, fg_hit = -0.5, "жадность", True
        else:
            fg_score, fg_label, fg_hit = 0.0, "нейтрально", False

        # --- SMA(200) ---
        sma = snap.sma_200
        price = snap.price
        if sma is None:
            sma_score, sma_label, sma_hit = 0.0, "нет данных", False
        else:
            # Check cross (we don't have historical crosses here, use simple above/below)
            pct_diff = (price - sma) / sma * 100
            if price > sma:
                sma_score, sma_label, sma_hit = 0.3, f"выше тренда (+{pct_diff:.1f}%)", True
            else:
                sma_score, sma_label, sma_hit = -0.3, f"ниже тренда ({pct_diff:.1f}%)", False

        # --- Volume (confirming — amplifies direction) ---
        vr = snap.volume_ratio
        base_direction = rsi_score * p.weight_rsi + fg_score * p.weight_fg + sma_score * p.weight_sma
        if vr is None:
            vol_score, vol_label, vol_hit = 0.0, "нет данных", False
        elif vr > 2.0:
            sign = 1 if base_direction >= 0 else -1
            vol_score = sign * 0.5
            vol_label = f"всплеск ×{vr:.1f}"
            vol_hit = True
        elif vr > p.volume_spike:
            sign = 1 if base_direction >= 0 else -1
            vol_score = sign * 0.3
            vol_label = f"подтверждение ×{vr:.1f}"
            vol_hit = abs(base_direction) > 0.1
        else:
            vol_score, vol_label, vol_hit = 0.0, f"нормальный ×{vr:.1f}", False

        total = (
            rsi_score * p.weight_rsi
            + fg_score * p.weight_fg
            + sma_score * p.weight_sma
            + vol_score * p.weight_volume
        )
        total = round(total, 4)

        hits = sum([rsi_hit, fg_hit, sma_hit, vol_hit])

        return ScoreBreakdown(
            rsi_score=rsi_score,
            rsi_value=rsi,
            rsi_label=rsi_label,
            rsi_hit=rsi_hit,
            fg_score=fg_score,
            fg_value=fg,
            fg_label=fg_label,
            fg_hit=fg_hit,
            sma_score=sma_score,
            sma_value=sma,
            sma_label=sma_label,
            sma_hit=sma_hit,
            vol_score=vol_score,
            vol_ratio=vr,
            vol_label=vol_label,
            vol_hit=vol_hit,
            total_score=total,
            hits=hits,
            confidence_bar=_confidence_bar(total),
        )

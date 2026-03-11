from __future__ import annotations
import math
import logging
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    entry_time: datetime
    exit_time: datetime
    symbol: str
    direction: str  # "buy" or "sell"
    entry_price: float
    exit_price: float
    pnl_pct: float
    pnl_abs: float


class Metrics:
    @staticmethod
    def win_rate(trades: list[BacktestTrade]) -> float:
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.pnl_pct > 0)
        return wins / len(trades)

    @staticmethod
    def max_drawdown(equity_curve: list[tuple[datetime, float]]) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0][1]
        max_dd = 0.0
        for _, val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @staticmethod
    def sharpe_ratio(returns: list[float], risk_free: float = 0.04) -> float | None:
        if len(returns) < 2:
            return None
        n = len(returns)
        mean = sum(returns) / n
        variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
        std = math.sqrt(variance)
        if std == 0:
            return None
        # Annualise (assuming daily returns)
        annual_mean = mean * 252
        annual_std = std * math.sqrt(252)
        return (annual_mean - risk_free) / annual_std

    @staticmethod
    def profit_factor(trades: list[BacktestTrade]) -> float:
        gross_profit = sum(t.pnl_abs for t in trades if t.pnl_abs > 0)
        gross_loss = abs(sum(t.pnl_abs for t in trades if t.pnl_abs < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

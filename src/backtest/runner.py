from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from src.backtest.loader import HistoricalLoader
from src.backtest.metrics import BacktestTrade, Metrics
from src.config import BacktestParams
from src.market.binance import Candle
from src.market.indicators import Indicators
from src.strategy.engine import SignalType, score_to_signal
from src.strategy.scorer import MarketSnapshot, Scorer

log = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl_pct: float
    max_drawdown_pct: float
    avg_trade_pnl_pct: float
    best_trade_pnl_pct: float
    worst_trade_pnl_pct: float
    sharpe: float | None
    hodl_pnl_pct: float
    vs_hodl: float
    equity_curve: list[tuple[datetime, float]]
    trades: list[BacktestTrade]


class BacktestRunner:
    def __init__(self, scorer: Scorer, loader: HistoricalLoader):
        self.scorer = scorer
        self.loader = loader
        self.ind = Indicators()

    async def run(self, symbol: str, days: int, config: BacktestParams) -> BacktestResult:
        candles = await self.loader.load_candles(symbol, "1d", days + 210)
        fg_history = await self.loader.load_fear_greed(days + 10)

        # Build FG lookup by date
        fg_by_date: dict[str, int] = {}
        for ts, val in fg_history:
            fg_by_date[ts.strftime("%Y-%m-%d")] = val

        capital = config.initial_capital
        pos_size_pct = config.position_size_pct / 100
        commission = config.commission_pct / 100

        trades: list[BacktestTrade] = []
        equity_curve: list[tuple[datetime, float]] = []
        open_positions: list[dict] = []

        if len(candles) < 15:
            log.warning("Not enough candles for backtest of %s", symbol)
            return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0, None, 0, 0, [], [])

        hodl_start_price = candles[210].close if len(candles) > 210 else candles[0].close
        hodl_end_price = candles[-1].close

        for i in range(210, len(candles)):
            candle = candles[i]
            closes = [c.close for c in candles[:i+1]]
            volumes = [c.volume for c in candles[:i+1]]

            rsi = self.ind.rsi(closes, 14)
            sma_200 = self.ind.sma(closes, 200) if len(closes) >= 200 else None
            ema_50 = self.ind.ema(closes, 50)
            vol_ratio = self.ind.volume_ratio(volumes, 20)

            date_str = candle.timestamp.strftime("%Y-%m-%d")
            fg = fg_by_date.get(date_str)

            snap = MarketSnapshot(
                symbol=symbol,
                price=candle.close,
                rsi=rsi,
                sma_200=sma_200,
                ema_50=ema_50,
                fear_greed=fg,
                volume_ratio=vol_ratio,
                change_24h_pct=None,
                timestamp=candle.timestamp,
            )
            breakdown = self.scorer.score(snap)
            sig = score_to_signal(breakdown.total_score)

            # Close positions if signal reverses
            remaining_positions = []
            for pos in open_positions:
                should_close = (
                    (pos["direction"] == "buy" and sig.is_bearish()) or
                    (pos["direction"] == "sell" and sig.is_bullish())
                )
                if should_close:
                    pnl_pct = (candle.close - pos["entry_price"]) / pos["entry_price"]
                    if pos["direction"] == "sell":
                        pnl_pct = -pnl_pct
                    pnl_pct -= 2 * commission  # entry + exit
                    pnl_abs = pos["size"] * pnl_pct
                    capital += pos["size"] + pnl_abs
                    trades.append(BacktestTrade(
                        entry_time=pos["entry_time"],
                        exit_time=candle.timestamp,
                        symbol=symbol,
                        direction=pos["direction"],
                        entry_price=pos["entry_price"],
                        exit_price=candle.close,
                        pnl_pct=round(pnl_pct * 100, 3),
                        pnl_abs=round(pnl_abs, 2),
                    ))
                else:
                    remaining_positions.append(pos)
            open_positions = remaining_positions

            # Open new position
            if sig.is_actionable() and len(open_positions) < 3:
                size = capital * pos_size_pct
                capital -= size
                direction = "buy" if sig.is_bullish() else "sell"
                open_positions.append({
                    "direction": direction,
                    "entry_price": candle.close,
                    "entry_time": candle.timestamp,
                    "size": size,
                })

            equity_curve.append((candle.timestamp, capital + sum(p["size"] for p in open_positions)))

        # Close remaining positions at last price
        if candles and open_positions:
            last = candles[-1]
            for pos in open_positions:
                pnl_pct = (last.close - pos["entry_price"]) / pos["entry_price"]
                if pos["direction"] == "sell":
                    pnl_pct = -pnl_pct
                pnl_pct -= 2 * commission
                pnl_abs = pos["size"] * pnl_pct
                capital += pos["size"] + pnl_abs
                trades.append(BacktestTrade(
                    entry_time=pos["entry_time"],
                    exit_time=last.timestamp,
                    symbol=symbol,
                    direction=pos["direction"],
                    entry_price=pos["entry_price"],
                    exit_price=last.close,
                    pnl_pct=round(pnl_pct * 100, 3),
                    pnl_abs=round(pnl_abs, 2),
                ))

        wins = sum(1 for t in trades if t.pnl_pct > 0)
        losses = len(trades) - wins
        win_rate = wins / len(trades) if trades else 0
        total_pnl_pct = (capital - config.initial_capital) / config.initial_capital * 100
        avg_pnl = sum(t.pnl_pct for t in trades) / len(trades) if trades else 0
        best = max((t.pnl_pct for t in trades), default=0)
        worst = min((t.pnl_pct for t in trades), default=0)
        max_dd = Metrics.max_drawdown(equity_curve) * 100
        daily_returns = []
        for j in range(1, len(equity_curve)):
            prev = equity_curve[j-1][1]
            curr = equity_curve[j][1]
            if prev > 0:
                daily_returns.append((curr - prev) / prev)
        sharpe = Metrics.sharpe_ratio(daily_returns)
        hodl_pct = (hodl_end_price - hodl_start_price) / hodl_start_price * 100

        return BacktestResult(
            total_trades=len(trades),
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            total_pnl_pct=round(total_pnl_pct, 2),
            max_drawdown_pct=round(max_dd, 2),
            avg_trade_pnl_pct=round(avg_pnl, 2),
            best_trade_pnl_pct=round(best, 2),
            worst_trade_pnl_pct=round(worst, 2),
            sharpe=round(sharpe, 3) if sharpe is not None else None,
            hodl_pnl_pct=round(hodl_pct, 2),
            vs_hodl=round(total_pnl_pct - hodl_pct, 2),
            equity_curve=equity_curve,
            trades=trades,
        )

import pytest
from datetime import datetime, timezone
from src.backtest.metrics import Metrics, BacktestTrade


def make_trade(pnl_pct, pnl_abs):
    return BacktestTrade(
        entry_time=datetime.now(timezone.utc),
        exit_time=datetime.now(timezone.utc),
        symbol="BTCUSDT",
        direction="buy",
        entry_price=60000,
        exit_price=60000,
        pnl_pct=pnl_pct,
        pnl_abs=pnl_abs,
    )


def test_win_rate_empty():
    assert Metrics.win_rate([]) == 0.0


def test_win_rate():
    trades = [make_trade(1, 100), make_trade(-1, -50), make_trade(2, 200)]
    assert Metrics.win_rate(trades) == pytest.approx(2/3)


def test_max_drawdown_empty():
    assert Metrics.max_drawdown([]) == 0.0


def test_max_drawdown():
    from datetime import datetime
    now = datetime.now(timezone.utc)
    curve = [(now, 10000), (now, 12000), (now, 8000), (now, 11000)]
    dd = Metrics.max_drawdown(curve)
    # Peak is 12000, low is 8000 → drawdown = (12000-8000)/12000 = 0.333
    assert dd == pytest.approx(1/3, rel=0.01)


def test_sharpe_none_on_single():
    assert Metrics.sharpe_ratio([0.01]) is None


def test_profit_factor():
    trades = [make_trade(5, 500), make_trade(-2, -200), make_trade(3, 300)]
    pf = Metrics.profit_factor(trades)
    assert pf == pytest.approx(4.0)

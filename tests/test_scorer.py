import pytest
from datetime import datetime, timezone
from src.config import StrategyParams
from src.strategy.scorer import Scorer, MarketSnapshot


def make_snap(**kwargs):
    defaults = dict(
        symbol="BTCUSDT",
        price=70000.0,
        rsi=None,
        sma_200=None,
        ema_50=None,
        fear_greed=None,
        volume_ratio=None,
        change_24h_pct=None,
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return MarketSnapshot(**defaults)


@pytest.fixture
def scorer():
    return Scorer(StrategyParams())


def test_strong_buy(scorer):
    # RSI=18 (+1.0×0.35), F&G=14 (+1.0×0.25), above SMA (+0.3×0.25), vol×2.5 (+0.5×0.15) → ≈ 0.8
    snap = make_snap(rsi=18, fear_greed=14, price=75000, sma_200=72000, volume_ratio=2.5)
    b = scorer.score(snap)
    assert b.total_score >= 0.6
    assert b.rsi_hit
    assert b.fg_hit


def test_strong_sell(scorer):
    snap = make_snap(rsi=82, fear_greed=88, price=85000, sma_200=72000, volume_ratio=2.1)
    b = scorer.score(snap)
    assert b.total_score < -0.3
    assert b.rsi_hit
    assert b.fg_hit


def test_neutral(scorer):
    snap = make_snap(rsi=50, fear_greed=50, price=70000, sma_200=70000)
    b = scorer.score(snap)
    assert abs(b.total_score) < 0.3


def test_no_data(scorer):
    snap = make_snap()
    b = scorer.score(snap)
    assert b.total_score == 0.0


def test_volume_amplifies(scorer):
    snap_no_vol = make_snap(rsi=25, fear_greed=20, price=65000, sma_200=72000, volume_ratio=None)
    snap_with_vol = make_snap(rsi=25, fear_greed=20, price=65000, sma_200=72000, volume_ratio=2.5)
    b_no = scorer.score(snap_no_vol)
    b_with = scorer.score(snap_with_vol)
    assert b_with.total_score > b_no.total_score


def test_confidence_bar(scorer):
    snap = make_snap(rsi=25, fear_greed=18, price=65000, sma_200=72000)
    b = scorer.score(snap)
    assert len(b.confidence_bar) == 10
    assert "█" in b.confidence_bar

import pytest
from src.market.indicators import Indicators


def test_rsi_not_enough_data():
    assert Indicators.rsi([1.0, 2.0], 14) is None


def test_rsi_all_gains():
    prices = [float(i) for i in range(1, 20)]
    result = Indicators.rsi(prices, 14)
    assert result is not None
    assert result > 70


def test_rsi_all_losses():
    prices = [float(20 - i) for i in range(20)]
    result = Indicators.rsi(prices, 14)
    assert result is not None
    assert result < 30


def test_rsi_known_value():
    # Flat prices → RSI undefined behavior but should not crash
    prices = [100.0] * 20
    result = Indicators.rsi(prices, 14)
    assert result is not None


def test_sma_not_enough():
    assert Indicators.sma([1.0, 2.0], 200) is None


def test_sma_correct():
    prices = [float(i) for i in range(1, 201)]
    result = Indicators.sma(prices, 200)
    assert result == pytest.approx(100.5)


def test_ema_basic():
    prices = [10.0] * 60
    result = Indicators.ema(prices, 50)
    assert result == pytest.approx(10.0, rel=0.01)


def test_volume_ratio():
    vols = [100.0] * 21 + [200.0]
    # Last volume is 200, avg of previous 20 is 100 → ratio 2.0
    result = Indicators.volume_ratio(vols, 20)
    assert result is not None
    # The last element is 200, previous 20 avg is ~100
    assert result > 1.0


def test_crossed_sma_up():
    closes = [95.0, 96.0, 97.0, 98.0, 99.0, 101.0]
    result = Indicators.crossed_sma(closes, 100.0, lookback=5)
    assert result == "up"


def test_crossed_sma_none():
    closes = [95.0, 96.0, 97.0, 98.0, 99.0, 99.5]
    result = Indicators.crossed_sma(closes, 100.0, lookback=5)
    assert result is None

import pytest
from datetime import datetime, timezone
from src.strategy.engine import Signal, SignalType
from src.strategy.scorer import ScoreBreakdown
from src.telegram.formatter import format_signal, format_check_summary


def make_signal(signal_type=SignalType.STRONG_BUY, score=0.65):
    b = ScoreBreakdown(
        rsi_score=0.5, rsi_value=25.0, rsi_label="перепродан", rsi_hit=True,
        fg_score=0.5, fg_value=18, fg_label="страх", fg_hit=True,
        sma_score=-0.3, sma_value=72000.0, sma_label="ниже тренда (-5.0%)", sma_hit=False,
        vol_score=0.3, vol_ratio=1.8, vol_label="подтверждение ×1.8", vol_hit=True,
        total_score=score, hits=3, confidence_bar="██████░░░░",
    )
    return Signal(
        type=signal_type,
        symbol="BTCUSDT",
        price=69500.0,
        breakdown=b,
        backtest_summary="Win Rate: 67% | Ср. +4.2%",
        ai_comment="Данные указывают на перепроданность.",
        timestamp=datetime.now(timezone.utc),
    )


def test_format_signal_contains_sections():
    sig = make_signal()
    text = format_signal(sig)
    assert "ПОКУПКА" in text
    assert "RSI" in text
    assert "Fear & Greed" in text
    assert "SMA" in text
    assert "Объём" in text
    assert "Сила:" in text
    assert "⚠️" in text
    assert "финансовый совет" in text


def test_format_signal_sell():
    sig = make_signal(SignalType.STRONG_SELL, score=-0.75)
    text = format_signal(sig)
    assert "ПРОДАЖА" in text


def test_format_check_summary():
    signals = [make_signal(SignalType.BUY), make_signal(SignalType.NEUTRAL, 0.0)]
    text = format_check_summary(signals)
    assert "Проверка" in text
    assert "BTC" in text

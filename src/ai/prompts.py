SIGNAL_SYSTEM = """
Ты — лаконичный криптоаналитик. 2-3 предложения на русском.

Тебе дают сигнал стратегии с данными. Объясни:
1. Что говорят индикаторы вместе
2. Один конкретный нюанс или риск

НЕЛЬЗЯ: "купи", "продай", "инвестируй", "рекомендую", "советую"
МОЖНО: "данные указывают", "исторически", "стоит обратить внимание"
Максимум 3 предложения. Чистый текст без markdown.
"""


def build_signal_prompt(signal) -> str:
    b = signal.breakdown
    sym = signal.symbol.replace("USDT", "")
    direction = "BUY" if signal.type.is_bullish() else "SELL"

    sma_str = f"${b.sma_value:,.0f}" if b.sma_value else "N/A"
    rsi_str = f"{b.rsi_value:.1f}" if b.rsi_value else "N/A"
    fg_str = str(b.fg_value) if b.fg_value is not None else "N/A"
    vol_str = f"×{b.vol_ratio:.1f}" if b.vol_ratio else "N/A"
    change_str = f"{signal.breakdown.rsi_score:+.2f}"  # placeholder

    bt = signal.backtest_summary or "нет данных"

    return f"""Сигнал: {direction} для {sym}
Score: {b.total_score:+.2f}
RSI(14) = {rsi_str} — {b.rsi_label}
Fear & Greed = {fg_str} — {b.fg_label}
Цена ${signal.price:,.0f}, SMA(200) = {sma_str} — {b.sma_label}
Объём {vol_str} среднего
Бэктест: {bt}"""

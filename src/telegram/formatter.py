from __future__ import annotations
from datetime import datetime, timezone

from src.strategy.engine import Signal, SignalType


def _coin_name(symbol: str) -> str:
    return symbol.replace("USDT", "")


def format_signal(signal: Signal) -> str:
    st = signal.type
    coin = _coin_name(signal.symbol)
    b = signal.breakdown

    # Header
    if st == SignalType.STRONG_BUY:
        header = f"🟢🟢 ПОКУПКА — {coin}"
    elif st == SignalType.BUY:
        header = f"🟢 ПОКУПКА — {coin}"
    elif st == SignalType.STRONG_SELL:
        header = f"🔴🔴 ПРОДАЖА — {coin}"
    elif st == SignalType.SELL:
        header = f"🔴 ПРОДАЖА — {coin}"
    else:
        header = f"⚪ НЕЙТРАЛЬНО — {coin}"

    price_str = f"${signal.price:,.0f}" if signal.price > 100 else f"${signal.price:,.4f}"

    # Breakdown rows
    rsi_str = f"{b.rsi_value:.1f}" if b.rsi_value is not None else "N/A"
    rsi_line = f"  {'✅' if b.rsi_hit else '❌'} RSI(14) = {rsi_str} — {b.rsi_label}"

    fg_str = str(b.fg_value) if b.fg_value is not None else "N/A"
    fg_line = f"  {'✅' if b.fg_hit else '❌'} Fear & Greed = {fg_str} — {b.fg_label}"

    sma_str = f"${b.sma_value:,.0f}" if b.sma_value else "нет данных"
    sma_line = f"  {'✅' if b.sma_hit else '❌'} {b.sma_label} (SMA={sma_str})"

    vol_str = f"×{b.vol_ratio:.1f}" if b.vol_ratio else "N/A"
    vol_line = f"  {'✅' if b.vol_hit else '❌'} Объём {vol_str} — {b.vol_label}"

    pct = round(abs(b.total_score) * 100)
    strength = f"Сила: {b.confidence_bar} {pct}%"

    bt_line = f"\n📈 Стратегия (365д): {signal.backtest_summary}" if signal.backtest_summary else ""

    ai_line = f"\n🤖 {signal.ai_comment}" if signal.ai_comment else ""

    ts = signal.timestamp.strftime("%d.%m.%Y %H:%M")

    return (
        f"{header}\n\n"
        f"💰 {price_str}\n\n"
        f"📊 Почему:\n"
        f"{rsi_line}\n"
        f"{fg_line}\n"
        f"{sma_line}\n"
        f"{vol_line}\n\n"
        f"{strength}"
        f"{bt_line}"
        f"{ai_line}\n\n"
        f"⚠️ Анализ данных, не финансовый совет.\n"
        f"🕐 {ts}"
    )


def format_check_summary(signals: list[Signal]) -> str:
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    lines = [f"🔍 Проверка — {now}\n"]
    for sig in signals:
        coin = _coin_name(sig.symbol)
        b = sig.breakdown
        st = sig.type

        if st == SignalType.STRONG_BUY:
            icon = "🟢🟢"
        elif st == SignalType.BUY:
            icon = "🟢"
        elif st == SignalType.STRONG_SELL:
            icon = "🔴🔴"
        elif st == SignalType.SELL:
            icon = "🔴"
        else:
            icon = "⚪"

        score_str = f"{b.total_score:+.2f}"
        rsi_str = f"{b.rsi_value:.0f}" if b.rsi_value else "?"
        fg_str = str(b.fg_value) if b.fg_value is not None else "?"
        sma_above = ">" if b.sma_score >= 0 else "<"
        vol_str = f"×{b.vol_ratio:.1f}" if b.vol_ratio else "?"

        lines.append(
            f"{icon} {coin}: {st.name} ({score_str})\n"
            f"  RSI={rsi_str} {'✅' if b.rsi_hit else ''} | "
            f"F&G={fg_str} {'✅' if b.fg_hit else ''} | "
            f"{sma_above}SMA {'✅' if b.sma_hit else '❌'} | "
            f"Vol {vol_str}"
        )
    return "\n".join(lines)


def format_backtest(symbol: str, result, days: int, capital: float) -> str:
    coin = _coin_name(symbol)
    r = result
    wins_icon = "🟢" if r.total_pnl_pct > 0 else "🔴"
    vs_icon = "✅" if r.vs_hodl > 0 else "❌"
    return (
        f"📊 Бэктест: {coin} ({days} дней)\n"
        f"Капитал: ${capital:,.0f} | Комиссия: 0.1%\n\n"
        f"Сделок: {r.total_trades} ({r.wins} 🟢 / {r.losses} 🔴)\n"
        f"Win Rate: {r.win_rate*100:.1f}%\n"
        f"P&L: ${r.total_pnl_pct/100*capital:,.0f} ({wins_icon} {r.total_pnl_pct:+.1f}%)\n"
        f"Просадка: -{r.max_drawdown_pct:.1f}%\n"
        f"Ср. сделка: {r.avg_trade_pnl_pct:+.1f}%\n"
        f"Лучшая: {r.best_trade_pnl_pct:+.1f}% | Худшая: {r.worst_trade_pnl_pct:+.1f}%\n\n"
        f"vs HODL: {r.hodl_pnl_pct:+.1f}%\n"
        f"Стратегия {'лучше' if r.vs_hodl > 0 else 'хуже'} на {r.vs_hodl:+.1f}% {vs_icon}\n\n"
        f"⚠️ Результаты на истории НЕ гарантируют будущее."
    )


def format_health(binance_ms: float | None, fg_val: int | None, fg_age_min: int,
                   gemini_ok: bool | None, db_count: int, uptime_sec: float,
                   signals_24h: int, signals_7d: int) -> str:
    binance_line = f"✅ Binance — ок ({binance_ms:.0f}мс)" if binance_ms else "❌ Binance — недоступен"
    fg_line = f"✅ Fear & Greed — {fg_val} (кэш {fg_age_min}м назад)" if fg_val else "❌ Fear & Greed — недоступен"
    if gemini_ok is None:
        gem_line = "⚠️ Gemini — нет ключа"
    elif gemini_ok:
        gem_line = "✅ Gemini — ок"
    else:
        gem_line = "❌ Gemini — ошибка"

    days = int(uptime_sec // 86400)
    hours = int((uptime_sec % 86400) // 3600)
    mins = int((uptime_sec % 3600) // 60)
    uptime_str = f"{days}д {hours}ч {mins}мин" if days > 0 else f"{hours}ч {mins}мин"

    return (
        f"🏥 Статус\n\n"
        f"{binance_line}\n"
        f"{fg_line}\n"
        f"{gem_line}\n"
        f"✅ SQLite — {db_count:,} записей\n"
        f"⏱ Uptime: {uptime_str}\n"
        f"🔔 Сигналов за 24ч: {signals_24h} | За неделю: {signals_7d}"
    )


def format_debug(symbol: str, snap, breakdown) -> str:
    coin = _coin_name(symbol)
    b = breakdown
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")

    price_str = f"${snap.price:,.0f}"
    sma_str = f"${b.sma_value:,.0f}" if b.sma_value else "N/A"
    ema_str = f"${snap.ema_50:,.0f}" if snap.ema_50 else "N/A"
    rsi_str = f"{b.rsi_value:.1f}" if b.rsi_value else "N/A"
    fg_str = str(b.fg_value) if b.fg_value is not None else "N/A"
    vol_ratio_str = f"{b.vol_ratio:.2f}x" if b.vol_ratio else "N/A"

    sma_pct = f"{(snap.price / b.sma_value - 1) * 100:.1f}%" if b.sma_value else "N/A"

    score = b.total_score
    signal_type = "NEUTRAL"
    if score >= 0.6:
        signal_type = "STRONG_BUY"
    elif score >= 0.3:
        signal_type = "BUY"
    elif score <= -0.6:
        signal_type = "STRONG_SELL"
    elif score <= -0.3:
        signal_type = "SELL"

    buy_dist = max(0.3 - score, 0) if score < 0.3 else 0
    sell_dist = max(score - (-0.3), 0) if score > -0.3 else 0

    return (
        f"🔬 {coin} — {now}\n\n"
        f"💰 {price_str}\n\n"
        f"Данные:\n"
        f"  RSI(14): {rsi_str}\n"
        f"  SMA(200): {sma_str}\n"
        f"  EMA(50): {ema_str}\n"
        f"  Цена/SMA: {sma_pct}\n"
        f"  F&G: {fg_str}\n"
        f"  Vol Ratio: {vol_ratio_str}\n\n"
        f"Скоринг:\n"
        f"  RSI:  {b.rsi_score:+.2f} × {0.35:.2f} = {b.rsi_score*0.35:+.3f}\n"
        f"  F&G:  {b.fg_score:+.2f} × {0.25:.2f} = {b.fg_score*0.25:+.3f}\n"
        f"  SMA:  {b.sma_score:+.2f} × {0.25:.2f} = {b.sma_score*0.25:+.3f}\n"
        f"  Vol:  {b.vol_score:+.2f} × {0.15:.2f} = {b.vol_score*0.15:+.3f}\n"
        f"  ───────────────────\n"
        f"  ИТОГО:         {score:+.3f}\n\n"
        f"Результат: {signal_type} (порог ±0.30)\n"
        f"До BUY: +{buy_dist:.3f} | До SELL: -{sell_dist:.3f}"
    )

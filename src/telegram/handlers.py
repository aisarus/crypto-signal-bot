from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from src.strategy.engine import SignalType
from src.telegram.formatter import (
    format_signal, format_check_summary, format_backtest,
    format_health, format_debug,
)

log = logging.getLogger(__name__)


class Handlers:
    def __init__(self, bot_instance):
        self.bot = bot_instance

    def _authorized(self, update: Update) -> bool:
        chat_id = str(update.effective_chat.id)
        allowed = str(self.bot.config.telegram_chat_id)
        if chat_id != allowed:
            log.warning("Unauthorized access from chat_id=%s", chat_id)
            return False
        return True

    async def start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        text = (
            "🤖 *Crypto Signal Bot*\n\n"
            "Мониторю крипторынок 24/7 и присылаю сигналы на основе:\n"
            "• RSI(14) — перекупленность/перепроданность\n"
            "• Fear & Greed Index — настроение рынка\n"
            "• SMA(200) — долгосрочный тренд\n"
            "• Объём — подтверждение движения\n\n"
            "📋 *Команды:*\n"
            "/check — проверить все монеты прямо сейчас\n"
            "/check BTC — проверить одну монету\n"
            "/signal — текущие сигналы\n"
            "/backtest BTC 365 — бэктест стратегии\n"
            "/health — статус системы\n"
            "/debug BTC — детальный дамп данных\n"
            "/coins — список монет\n"
            "/params — параметры стратегии\n"
            "/help — список команд"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def help_cmd(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        await self.start(update, ctx)

    async def check(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        args = ctx.args or []
        await update.message.reply_text("⏳ Обновляю данные и проверяю рынок...")

        try:
            cfg = self.bot.config
            if args:
                symbol = args[0].upper()
                if not symbol.endswith("USDT"):
                    symbol += "USDT"
                signals = await self.bot.engine.force_check(symbol=symbol, coins=[symbol])
            else:
                signals = await self.bot.engine.force_check(coins=cfg.coins)

            if not signals:
                await update.message.reply_text("❌ Не удалось получить данные.")
                return

            # Always show summary
            summary = format_check_summary(signals)
            await update.message.reply_text(summary)

            # Send full signal for actionable ones
            for sig in signals:
                if sig.type != SignalType.NEUTRAL:
                    # Add AI comment
                    if self.bot.gemini:
                        from src.ai.prompts import SIGNAL_SYSTEM, build_signal_prompt
                        prompt = build_signal_prompt(sig)
                        ai_text = await self.bot.gemini.generate(prompt, SIGNAL_SYSTEM)
                        sig.ai_comment = ai_text

                    text = format_signal(sig)
                    await update.message.reply_text(text)

                    # Chart
                    try:
                        candles = await self.bot.price_source.get_klines(sig.symbol, "1d", 60)
                        if candles:
                            img = self.bot.chart.generate(sig, candles)
                            if img:
                                await update.message.reply_photo(img)
                    except Exception as e:
                        log.warning("Chart error: %s", e)

        except Exception as e:
            log.error("Check error: %s", e)
            await update.message.reply_text(f"❌ Ошибка: {e}")

    async def signal_cmd(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        args = ctx.args or []
        try:
            cfg = self.bot.config
            if args:
                symbol = args[0].upper()
                if not symbol.endswith("USDT"):
                    symbol += "USDT"
                signals = [await self.bot.engine.evaluate(symbol)]
            else:
                signals = await self.bot.engine.evaluate_all()

            if not signals:
                await update.message.reply_text("Нет данных.")
                return

            summary = format_check_summary(signals)
            await update.message.reply_text(summary)
        except Exception as e:
            log.error("Signal error: %s", e)
            await update.message.reply_text(f"❌ Ошибка: {e}")

    async def backtest(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        args = ctx.args or []
        symbol = (args[0].upper() if args else "BTC")
        if not symbol.endswith("USDT"):
            symbol += "USDT"
        days = int(args[1]) if len(args) > 1 else self.bot.config.backtest.default_days
        days = max(30, min(days, 1000))

        await update.message.reply_text(f"⏳ Запускаю бэктест {symbol.replace('USDT','')} {days}д...")
        try:
            from src.backtest.runner import BacktestRunner
            from src.backtest.loader import HistoricalLoader
            loader = HistoricalLoader(self.bot.price_source, self.bot.fg)
            runner = BacktestRunner(self.bot.engine.scorer, loader)
            result = await runner.run(symbol, days, self.bot.config.backtest)
            text = format_backtest(symbol, result, days, self.bot.config.backtest.initial_capital)
            await update.message.reply_text(text)
        except Exception as e:
            log.error("Backtest error: %s", e)
            await update.message.reply_text(f"❌ Ошибка бэктеста: {e}")

    async def health(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        try:
            source_name, source_ms = await self.bot.price_source.ping()

            fg_val = None
            fg_age = 0
            try:
                fg_val = await self.bot.fg.get_current()
                if self.bot.fg._cache_ts:
                    import time as _time
                    fg_age = int((_time.monotonic() - self.bot.fg._cache_ts) / 60)
            except Exception:
                pass

            gemini_ok = None
            if self.bot.gemini:
                try:
                    result = await self.bot.gemini.generate("ping", max_tokens=5)
                    gemini_ok = result is not None
                except Exception:
                    gemini_ok = False

            db_count = await self.bot.store.get_record_count()
            uptime = time.monotonic() - self.bot.start_time
            sig_24h = await self.bot.store.get_signal_count(24)
            sig_7d = await self.bot.store.get_signal_count(24 * 7)

            text = format_health(source_ms, fg_val, fg_age, gemini_ok, db_count, uptime, sig_24h, sig_7d)
            # Prepend source info
            src_line = f"📡 Источник: {source_name}"
            if source_ms:
                src_line += f" ({source_ms:.0f}мс)"
            text = src_line + "\n\n" + text
            await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")

    async def debug(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        args = ctx.args or ["BTC"]
        symbol = args[0].upper()
        if not symbol.endswith("USDT"):
            symbol += "USDT"
        try:
            snap = await self.bot.engine.build_snapshot(symbol)
            breakdown = self.bot.engine.scorer.score(snap)
            cooldown_status = self.bot.cooldown.get_status(symbol)
            text = format_debug(symbol, snap, breakdown)
            text += f"\nКулдаун: {cooldown_status['status']}"
            await update.message.reply_text(text)
        except Exception as e:
            log.error("Debug error: %s", e)
            await update.message.reply_text(f"❌ {e}")

    async def coins(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        coin_list = "\n".join(f"• {c}" for c in self.bot.config.coins)
        await update.message.reply_text(f"📋 Монеты:\n{coin_list}")

    async def add_coin(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        if not ctx.args:
            await update.message.reply_text("Использование: /add DOGEUSDT")
            return
        symbol = ctx.args[0].upper()
        if not symbol.endswith("USDT"):
            symbol += "USDT"
        # Validate against CoinGecko SYMBOL_MAP when Binance unavailable
        if not self.bot.price_source.supports_symbol(symbol):
            from src.market.coingecko import SYMBOL_MAP
            supported = ", ".join(s.replace("USDT", "") for s in SYMBOL_MAP)
            await update.message.reply_text(
                f"⚠️ {symbol} не поддерживается в режиме CoinGecko.\n"
                f"Доступны: {supported}"
            )
            return
        if symbol not in self.bot.config.coins:
            self.bot.config.coins.append(symbol)
            await update.message.reply_text(f"✅ {symbol} добавлен")
        else:
            await update.message.reply_text(f"⚠️ {symbol} уже в списке")

    async def remove_coin(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        if not ctx.args:
            await update.message.reply_text("Использование: /remove DOGEUSDT")
            return
        symbol = ctx.args[0].upper()
        if not symbol.endswith("USDT"):
            symbol += "USDT"
        if symbol in self.bot.config.coins:
            self.bot.config.coins.remove(symbol)
            await update.message.reply_text(f"✅ {symbol} удалён")
        else:
            await update.message.reply_text(f"⚠️ {symbol} не найден")

    async def params(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        p = self.bot.config.strategy
        text = (
            f"⚙️ Параметры стратегии:\n\n"
            f"RSI период: {p.rsi_period}\n"
            f"RSI перепродан: ≤{p.rsi_oversold}\n"
            f"RSI перекуплен: ≥{p.rsi_overbought}\n"
            f"F&G страх: ≤{p.fg_fear}\n"
            f"F&G жадность: ≥{p.fg_greed}\n"
            f"SMA период: {p.sma_period}\n"
            f"Volume spike: ×{p.volume_spike}\n\n"
            f"Веса:\n"
            f"  RSI: {p.weight_rsi}\n"
            f"  F&G: {p.weight_fg}\n"
            f"  SMA: {p.weight_sma}\n"
            f"  Vol: {p.weight_volume}\n\n"
            f"Min confidence: {p.min_confidence}\n"
            f"Кулдаун: {p.cooldown_hours}ч / {p.strong_cooldown_hours}ч"
        )
        await update.message.reply_text(text)

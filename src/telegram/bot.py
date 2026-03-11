from __future__ import annotations
import asyncio
import logging
import time

from telegram import Bot
from telegram.ext import Application, CommandHandler

from src.config import Config
from src.telegram.charts import SignalChart
from src.telegram.handlers import Handlers

log = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, config: Config, engine, cooldown, gemini, store, binance, fg):
        self.config = config
        self.engine = engine
        self.cooldown = cooldown
        self.gemini = gemini
        self.store = store
        self.binance = binance
        self.fg = fg
        self.chart = SignalChart()
        self.start_time = time.monotonic()

        self._app = Application.builder().token(config.telegram_token).build()
        h = Handlers(self)
        self._app.add_handler(CommandHandler("start", h.start))
        self._app.add_handler(CommandHandler("help", h.help_cmd))
        self._app.add_handler(CommandHandler("check", h.check))
        self._app.add_handler(CommandHandler("signal", h.signal_cmd))
        self._app.add_handler(CommandHandler("backtest", h.backtest))
        self._app.add_handler(CommandHandler("health", h.health))
        self._app.add_handler(CommandHandler("debug", h.debug))
        self._app.add_handler(CommandHandler("coins", h.coins))
        self._app.add_handler(CommandHandler("add", h.add_coin))
        self._app.add_handler(CommandHandler("remove", h.remove_coin))
        self._app.add_handler(CommandHandler("params", h.params))

    async def send_text(self, text: str) -> None:
        try:
            await self._app.bot.send_message(
                chat_id=self.config.telegram_chat_id,
                text=text,
            )
        except Exception as e:
            log.error("Failed to send message: %s", e)

    async def send_signal(self, signal, with_chart: bool = True) -> None:
        from src.telegram.formatter import format_signal
        text = format_signal(signal)
        await self.send_text(text)
        if with_chart:
            try:
                candles = await self.binance.get_klines(signal.symbol, "1d", 60)
                if candles:
                    img = self.chart.generate(signal, candles)
                    if img:
                        await self._app.bot.send_photo(
                            chat_id=self.config.telegram_chat_id,
                            photo=img,
                        )
            except Exception as e:
                log.warning("Chart send error: %s", e)

    async def start_polling(self) -> None:
        log.info("Starting Telegram polling...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        # Run forever
        try:
            await asyncio.Event().wait()
        finally:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

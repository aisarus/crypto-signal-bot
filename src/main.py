from __future__ import annotations
import asyncio
import logging
import signal as _signal
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)


async def price_loop(config, price_source, store):
    """Collect prices every check_interval_sec."""
    while True:
        try:
            prices = await price_source.get_all_prices(config.coins)
            ts = datetime.now(timezone.utc)
            for symbol, price in prices.items():
                await store.save_price(symbol, price, 0, ts)
            log.debug("Prices updated: %d coins", len(prices))
        except Exception as e:
            log.error("price_loop error: %s", e)
        await asyncio.sleep(config.check_interval_sec)


async def signal_loop(config, engine, cooldown, gemini, bot, store):
    """Check signals every signal_interval_sec."""
    await asyncio.sleep(60)
    while True:
        try:
            # Refresh daily candles (1 request per coin, 3s pause between)
            for symbol in config.coins:
                try:
                    candles_1d = await engine.price_source.get_klines(symbol, "1d", 200)
                    await store.save_candles(symbol, "1d", candles_1d)
                except Exception as e:
                    log.warning("signal_loop candle refresh error for %s: %s", symbol, e)
                await asyncio.sleep(3)

            signals = await engine.evaluate_all()
            for sig in signals:
                if sig.type.is_actionable() and cooldown.can_send(sig.symbol, sig.type):
                    if gemini:
                        from src.ai.prompts import SIGNAL_SYSTEM, build_signal_prompt
                        try:
                            prompt = build_signal_prompt(sig)
                            sig.ai_comment = await gemini.generate(prompt, SIGNAL_SYSTEM)
                        except Exception as e:
                            log.warning("Gemini error for %s: %s", sig.symbol, e)

                    await bot.send_signal(sig)
                    cooldown.record(sig.symbol, sig.type)
                    await store.save_signal_log(sig.symbol, sig.type.value, sig.breakdown.total_score, sig.timestamp)
                    log.info("Signal sent: %s %s score=%.3f", sig.symbol, sig.type.value, sig.breakdown.total_score)
        except Exception as e:
            log.error("signal_loop error: %s", e)
        await asyncio.sleep(config.signal_interval_sec)


async def backtest_cache_loop(config, scorer, store, price_source, fg):
    """Refresh backtest cache daily."""
    from src.backtest.runner import BacktestRunner
    from src.backtest.loader import HistoricalLoader
    loader = HistoricalLoader(price_source, fg)
    runner = BacktestRunner(scorer, loader)

    await asyncio.sleep(300)
    while True:
        try:
            for symbol in config.coins:
                try:
                    result = await runner.run(symbol, config.backtest.default_days, config.backtest)
                    summary = (
                        f"Win Rate: {result.win_rate*100:.0f}% | "
                        f"Ср. {result.avg_trade_pnl_pct:+.1f}%"
                    )
                    await store.save_backtest_cache(symbol, config.backtest.default_days, "", summary)
                    log.info("Backtest cache updated: %s %s", symbol, summary)
                    await asyncio.sleep(5)
                except Exception as e:
                    log.error("Backtest cache error for %s: %s", symbol, e)
        except Exception as e:
            log.error("backtest_cache_loop error: %s", e)
        await asyncio.sleep(24 * 3600)


async def cleanup_loop(store):
    """Cleanup old data every hour."""
    while True:
        await asyncio.sleep(3600)
        try:
            await store.cleanup(keep_days=90)
        except Exception as e:
            log.error("cleanup_loop error: %s", e)


async def main():
    from src.config import load_config
    from src.logger import setup_logging
    from src.market.store import MarketStore
    from src.market.binance import BinanceClient
    from src.market.coingecko import CoinGeckoClient
    from src.market.price_source import PriceSource
    from src.market.fear_greed import FearGreedIndex
    from src.market.indicators import Indicators
    from src.strategy.scorer import Scorer
    from src.strategy.engine import StrategyEngine
    from src.strategy.cooldown import Cooldown
    from src.ai.gemini import GeminiClient
    from src.telegram.bot import TelegramBot

    config = load_config()
    setup_logging(config.log_level)

    log.info("Starting Crypto Signal Bot v3.0")

    store = MarketStore(config.db_path)
    binance = BinanceClient()
    coingecko = CoinGeckoClient()
    price_source = PriceSource(binance, coingecko)
    fg = FearGreedIndex()
    indicators = Indicators()
    scorer = Scorer(config.strategy)
    engine = StrategyEngine(scorer, store, price_source, fg, indicators)
    cooldown = Cooldown(config.strategy.cooldown_hours, config.strategy.strong_cooldown_hours)
    gemini = GeminiClient(config.gemini_api_key) if config.gemini_api_key else None
    bot = TelegramBot(config, engine, cooldown, gemini, store, price_source, fg)

    await store.init_db()

    # Check data source availability
    log.info("Проверка источника данных...")
    await price_source.init()

    # Initial data load
    log.info("Loading historical data (200 daily + 50 hourly candles) via %s...", price_source.source_name)
    for symbol in config.coins:
        try:
            candles_1d = await price_source.get_klines(symbol, "1d", 200)
            await store.save_candles(symbol, "1d", candles_1d)
            candles_1h = await price_source.get_klines(symbol, "1h", 50)
            await store.save_candles(symbol, "1h", candles_1h)
            log.info("Loaded %s: %d daily, %d hourly candles", symbol, len(candles_1d), len(candles_1h))
        except Exception as e:
            log.error("Failed to load initial data for %s: %s", symbol, e)

    log.info("Historical data loaded. Starting bot...")

    source_note = (
        f"📡 Источник: {price_source.source_name}"
        if price_source.source_name == "CoinGecko"
        else ""
    )
    startup_msg = f"🤖 Signal Bot запущен\n{source_note}\n/check — проверить сейчас".strip()
    await bot.send_text(startup_msg)

    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_signal(sig):
        log.info("Shutdown signal received: %s", sig)
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (_signal.SIGINT, _signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            pass  # Windows

    async def run_all():
        tasks = [
            asyncio.create_task(price_loop(config, price_source, store)),
            asyncio.create_task(signal_loop(config, engine, cooldown, gemini, bot, store)),
            asyncio.create_task(backtest_cache_loop(config, scorer, store, price_source, fg)),
            asyncio.create_task(cleanup_loop(store)),
            asyncio.create_task(bot.start_polling()),
        ]
        try:
            await shutdown_event.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    try:
        await run_all()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        log.info("Shutting down...")
        try:
            await bot.send_text("🔴 Bot остановлен")
        except Exception:
            pass
        await price_source.close()
        await fg.close()
        if gemini:
            await gemini.close()
        await store.close()
        log.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())

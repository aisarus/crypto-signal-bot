from __future__ import annotations
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrategyParams(BaseModel):
    rsi_period: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    fg_fear: int = 25
    fg_greed: int = 75
    sma_period: int = 200
    volume_spike: float = 1.5
    weight_rsi: float = 0.35
    weight_fg: float = 0.25
    weight_sma: float = 0.25
    weight_volume: float = 0.15
    min_confidence: float = 0.3
    cooldown_hours: int = 8
    strong_cooldown_hours: int = 4


class BacktestParams(BaseModel):
    default_days: int = 365
    initial_capital: float = 10000
    position_size_pct: float = 10
    commission_pct: float = 0.1
    cache_refresh_hours: int = 24


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    telegram_token: str
    telegram_chat_id: str
    gemini_api_key: str = ""
    coins: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    check_interval_sec: int = 300
    signal_interval_sec: int = 3600
    strategy: StrategyParams = StrategyParams()
    backtest: BacktestParams = BacktestParams()
    db_path: str = "data/signals.db"
    log_level: str = "INFO"
    timezone: str = "Asia/Jerusalem"


def load_config() -> Config:
    """Load config from config.yaml (if exists), then override with env vars."""
    yaml_data: dict[str, Any] = {}
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path) as f:
            yaml_data = yaml.safe_load(f) or {}

    # Convert nested dicts for pydantic
    return Config(**yaml_data)

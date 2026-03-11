from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone

from src.strategy.engine import SignalType

log = logging.getLogger(__name__)


class Cooldown:
    def __init__(self, normal_hours: int = 8, strong_hours: int = 4):
        self.normal_hours = normal_hours
        self.strong_hours = strong_hours
        # symbol -> {"last_type": SignalType, "last_time": datetime}
        self._state: dict[str, dict] = {}

    def _cooldown_hours(self, signal_type: SignalType) -> int:
        if signal_type in (SignalType.STRONG_BUY, SignalType.STRONG_SELL):
            return self.strong_hours
        return self.normal_hours

    def can_send(self, symbol: str, signal_type: SignalType) -> bool:
        if signal_type == SignalType.NEUTRAL:
            return False
        state = self._state.get(symbol)
        if state is None:
            return True
        last_type = state["last_type"]
        last_time = state["last_time"]
        # Direction change: reset immediately
        if last_type.is_bullish() and signal_type.is_bearish():
            return True
        if last_type.is_bearish() and signal_type.is_bullish():
            return True
        # Same direction: check cooldown
        hours = self._cooldown_hours(signal_type)
        return datetime.now(timezone.utc) - last_time > timedelta(hours=hours)

    def record(self, symbol: str, signal_type: SignalType) -> None:
        self._state[symbol] = {
            "last_type": signal_type,
            "last_time": datetime.now(timezone.utc),
        }

    def reset(self, symbol: str) -> None:
        self._state.pop(symbol, None)

    def get_status(self, symbol: str) -> dict:
        state = self._state.get(symbol)
        if state is None:
            return {"status": "свободен", "last_type": None, "last_time": None}
        hours = self._cooldown_hours(state["last_type"])
        elapsed = datetime.now(timezone.utc) - state["last_time"]
        remaining = timedelta(hours=hours) - elapsed
        if remaining.total_seconds() <= 0:
            status = "свободен"
            remaining_str = "0"
        else:
            mins = int(remaining.total_seconds() / 60)
            status = f"кулдаун {mins}м"
            remaining_str = f"{mins}м"
        return {
            "status": status,
            "last_type": state["last_type"].value,
            "last_time": state["last_time"].isoformat(),
            "remaining": remaining_str,
        }

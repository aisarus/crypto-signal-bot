import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from src.strategy.cooldown import Cooldown
from src.strategy.engine import SignalType


def test_can_send_first_time():
    cd = Cooldown()
    assert cd.can_send("BTC", SignalType.BUY)


def test_cannot_send_within_cooldown():
    cd = Cooldown(normal_hours=8)
    cd.record("BTC", SignalType.BUY)
    assert not cd.can_send("BTC", SignalType.BUY)


def test_can_send_after_cooldown():
    cd = Cooldown(normal_hours=8)
    cd.record("BTC", SignalType.BUY)
    # Manually set the time to past the cooldown
    cd._state["BTC"]["last_time"] = datetime.now(timezone.utc) - timedelta(hours=9)
    assert cd.can_send("BTC", SignalType.BUY)


def test_direction_change_resets():
    cd = Cooldown(normal_hours=8)
    cd.record("BTC", SignalType.BUY)
    # Direction change should allow immediate send
    assert cd.can_send("BTC", SignalType.SELL)


def test_neutral_never_sends():
    cd = Cooldown()
    assert not cd.can_send("BTC", SignalType.NEUTRAL)


def test_strong_cooldown_shorter():
    cd = Cooldown(normal_hours=8, strong_hours=4)
    cd.record("BTC", SignalType.STRONG_BUY)
    cd._state["BTC"]["last_time"] = datetime.now(timezone.utc) - timedelta(hours=5)
    assert cd.can_send("BTC", SignalType.STRONG_BUY)


def test_get_status():
    cd = Cooldown()
    status = cd.get_status("BTC")
    assert status["status"] == "свободен"

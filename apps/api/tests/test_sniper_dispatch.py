import time

from services.sniper_dispatch import is_stuck_starting


def test_is_stuck_starting_running_zero_checks():
    data = {
        "state": "running",
        "checks_done": 0,
        "started_at": time.time() - 100,
        "running_started_at": time.time() - 100,
    }
    assert is_stuck_starting(data) is True


def test_is_stuck_starting_not_yet():
    data = {
        "state": "running",
        "checks_done": 0,
        "started_at": time.time() - 5,
        "running_started_at": time.time() - 5,
    }
    assert is_stuck_starting(data) is False


def test_is_stuck_starting_with_checks():
    data = {
        "state": "running",
        "checks_done": 10,
        "started_at": time.time() - 60,
    }
    assert is_stuck_starting(data) is False


def test_is_stuck_starting_with_proxy_misses_is_active():
    data = {
        "state": "running",
        "checks_done": 0,
        "proxy_misses": 40,
        "started_at": time.time() - 120,
        "running_started_at": time.time() - 120,
    }
    assert is_stuck_starting(data) is False

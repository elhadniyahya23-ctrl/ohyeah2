from sniper.proxy import ProxyRotator
from services.turbo_sniper_service import (
    DISCORD_MAX_WORKERS,
    DISCORD_MAX_WORKERS_MULTI,
    DISCORD_MIN_WORKERS,
)


def test_discord_workers_budget_flashproxy():
    rot = ProxyRotator.from_lines(["lite.flashproxy.io:6969:ocglomsgkn:bevtimvqdi"])
    line_cap = min(
        DISCORD_MAX_WORKERS_MULTI,
        max(DISCORD_MAX_WORKERS, rot.line_count * 6),
    )
    effective = max(DISCORD_MIN_WORKERS, min(line_cap, rot.workers_budget))
    assert effective == 6


def test_discord_workers_budget_dataimpulse():
    rot = ProxyRotator.from_lines(
        ["c06e5d5a6a4fa37f8eeb__cr.us:pass@gw.dataimpulse.com:823"]
    )
    line_cap = min(
        DISCORD_MAX_WORKERS_MULTI,
        max(DISCORD_MAX_WORKERS, rot.line_count * 6),
    )
    effective = max(DISCORD_MIN_WORKERS, min(line_cap, rot.workers_budget))
    assert effective == 6


def test_discord_workers_scale_with_multi_provider():
    flash = "lite.flashproxy.io:6969:ocglomsgkn:bevtimvqdi"
    data = "c06e5d5a6a4fa37f8eeb__cr.us:pass@gw.dataimpulse.com:823"
    adam = "lite.proxyserver.bot:6969:adamuser:adampass"
    rot = ProxyRotator.from_lines([flash, data, adam])
    assert rot.line_count == 3
    assert rot.workers_budget == 18
    line_cap = min(
        DISCORD_MAX_WORKERS_MULTI,
        max(DISCORD_MAX_WORKERS, rot.line_count * 6),
    )
    effective = max(DISCORD_MIN_WORKERS, min(160, rot.workers_budget, line_cap))
    assert line_cap == 18
    assert effective == 18


def test_discord_min_workers_floor():
    assert DISCORD_MIN_WORKERS == 4
    assert DISCORD_MAX_WORKERS == 10
    assert DISCORD_MAX_WORKERS_MULTI == 36

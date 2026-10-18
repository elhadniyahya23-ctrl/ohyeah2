from urllib.parse import unquote

from sniper.proxy import ProxyConfig, ProxyRotator
from sniper.registry import get_workers
from services.turbo_sniper_service import DISCORD_MIN_WORKERS


FLASH = "lite.flashproxy.io:6969:ocglomsgkn:bevtimvqdi"
DATA = "c06e5d5a6a4fa37f8eeb__cr.us:234f0ba20a36aadc@gw.dataimpulse.com:823"


def test_flashproxy_host_port_user_pass():
    cfg = ProxyConfig.from_line(FLASH)
    assert cfg is not None
    assert cfg.host == "lite.flashproxy.io"
    assert cfg.workers_budget() == 6
    assert "ocglomsgkn-session-" in unquote(cfg.rotate_url())


def test_dataimpulse_user_pass_at_host():
    cfg = ProxyConfig.from_line(DATA)
    assert cfg is not None
    assert cfg.host == "gw.dataimpulse.com"
    assert cfg.workers_budget() == 6
    decoded_user = unquote(cfg.rotate_url().split("://", 1)[1].split(":", 1)[0])
    assert decoded_user.startswith("c06e5d5a6a4fa37f8eeb__cr.us__sessid.")


def test_http_uri_format():
    cfg = ProxyConfig.from_line("http://user:pass@proxy.example.com:8080")
    assert cfg is not None
    assert cfg.rotate_url() == "http://user:pass@proxy.example.com:8080"


def test_rotator_budget_sums_lines():
    rot = ProxyRotator.from_lines([FLASH, DATA])
    assert rot.line_count == 2
    assert rot.workers_budget == 12


def test_flashproxy_reuses_bounded_session_pool():
    cfg = ProxyConfig.from_line(FLASH)
    assert cfg is not None
    users = []
    for _ in range(140):
        url = cfg.rotate_url()
        user = unquote(url.split("://", 1)[1].split(":", 1)[0])
        users.append(user)
    # 128 sticky sessions then wrap — not unique UUIDs every time.
    assert len(set(users)) == 128
    assert all("-session-ps" in u for u in users)


def test_rotator_fair_share_across_lines():
    rot = ProxyRotator.from_lines([FLASH, DATA])
    picks = [rot.next_lease()[1] for _ in range(40)]
    # Round-robin: both providers get roughly half the leases.
    assert abs(picks.count(0) - picks.count(1)) <= 2


def test_rotator_skips_dead_line_when_alt_alive():
    rot = ProxyRotator.from_lines([FLASH, DATA])
    for _ in range(20):
        rot.report(0, "proxy_late")
    for _ in range(6):
        rot.report(1, "taken")
    picks = [rot.next_lease()[1] for _ in range(30)]
    assert picks.count(1) > picks.count(0)


def test_proxyserver_bot_uses_flash_sessions():
    cfg = ProxyConfig.from_line("lite.proxyserver.bot:6969:user:pass")
    assert cfg is not None
    assert cfg._provider_session_mode() == "flashproxy"
    assert "-session-" in unquote(cfg.rotate_url())


def test_discord_min_workers_floor():
    assert DISCORD_MIN_WORKERS == 4
    assert get_workers("discord", 160) == 160


def test_normalize_splits_space_separated_providers():
    from services.user_store import normalize_proxy_lines

    glued = [
        "lite.flashproxy.io:6969:u1:p1 lite.flashproxy.io:6969:u2:p2 "
        "user:pass@gw.dataimpulse.com:823 lite.proxyserver.bot:6969:adam:pass"
    ]
    out = normalize_proxy_lines(glued)
    assert len(out) == 4
    assert out[0] == "lite.flashproxy.io:6969:u1:p1"
    assert out[1] == "lite.flashproxy.io:6969:u2:p2"
    assert out[2] == "gw.dataimpulse.com:823:user:pass"
    assert out[3] == "lite.proxyserver.bot:6969:adam:pass"


def test_normalize_splits_comma_separated_providers():
    from services.user_store import normalize_proxy_lines

    out = normalize_proxy_lines(
        ["lite.flashproxy.io:6969:u1:p1, user:pass@gw.dataimpulse.com:823"]
    )
    assert len(out) == 2


def test_normalize_splits_glued_proxy_pastes():
    from services.user_store import normalize_proxy_lines

    glued = [
        "lite.flashproxy.io:6969:dqi2naiqn9:cfgqo8gai8",
        "lite.flashproxy.io:6969:f10iixxzxa:nevjw9phc3http://f10iixxzxa:nevjw9phc3@lite.flashproxy.io:6969",
        "http://f10iixxzxa:nevjw9phc3@lite.flashproxy.io:6969http://f10iixxzxa:nevjw9phc3@lite.flashproxy.io:6969",
        "http://f10iixxzxa:nevjw9phc3@lite.flashproxy.io:6969",
        "lite.flashproxy.io:6969:f10iixxzxa:nevjw9phc3",
        "not-a-proxy",
    ]
    out = normalize_proxy_lines(glued)
    assert out == [
        "lite.flashproxy.io:6969:dqi2naiqn9:cfgqo8gai8",
        "lite.flashproxy.io:6969:f10iixxzxa:nevjw9phc3",
    ]


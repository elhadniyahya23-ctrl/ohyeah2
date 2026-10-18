from sniper.discord_checker import DiscordChecker
from sniper.proxy import ProxyConfig


def test_discord_checker_platform():
    assert DiscordChecker.platform == "discord"


def test_paid_proxy_stays_plain():
    cfg = ProxyConfig.from_line("host:1:user:pass", rotate_sessions=False)
    assert cfg is not None
    assert cfg.rotate_url() == "http://user:pass@host:1"

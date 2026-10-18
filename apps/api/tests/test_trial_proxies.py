from services.trial_proxies import get_trial_proxies


def test_get_trial_proxies_empty_by_default(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "trial_proxy_lines", "")
    assert get_trial_proxies() == []


def test_get_trial_proxies_comma_separated(monkeypatch):
    from config import settings

    monkeypatch.setattr(
        settings,
        "trial_proxy_lines",
        "user:pass@host1:8080, user:pass@host2:8080",
    )
    proxies = get_trial_proxies()
    assert len(proxies) == 2
    assert "host1" in proxies[0]
    assert "host2" in proxies[1]


def test_get_trial_proxies_newline_separated(monkeypatch):
    from config import settings

    monkeypatch.setattr(
        settings,
        "trial_proxy_lines",
        "user:pass@a:1\nuser:pass@b:2\n",
    )
    assert len(get_trial_proxies()) == 2

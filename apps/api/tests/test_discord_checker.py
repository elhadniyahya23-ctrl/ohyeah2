from sniper.discord_checker import DiscordChecker
from sniper.turbo_engine import Status


class _FakeResp:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text else ("" if payload is None else str(payload))
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_discord_invalid_format_is_taken():
    result = DiscordChecker().check("x", "http://user:pass@proxy:1")
    assert result.status == Status.TAKEN
    assert result.detail == "invalid_format"


def test_discord_suggestion_mismatch_is_taken(monkeypatch):
    def fake_get(url, **kwargs):
        return _FakeResp(200, {"username": "othername"})

    class Sess:
        def get(self, *a, **k):
            return fake_get(*a, **k)

        def post(self, *a, **k):
            raise AssertionError("attempt must not run on hot path")

    monkeypatch.setattr("sniper.discord_checker.get_session", lambda: Sess())
    monkeypatch.setattr("sniper.discord_checker.proxy_dict", lambda url: {})

    result = DiscordChecker().check("coolname", "http://user:pass@proxy:1")
    assert result.status == Status.TAKEN
    assert "suggested=" in (result.detail or "")


def test_discord_suggestion_hit_is_available(monkeypatch):
    def fake_get(url, **kwargs):
        return _FakeResp(200, {"username": "coolname"})

    class Sess:
        def get(self, *a, **k):
            return fake_get(*a, **k)

        def post(self, *a, **k):
            raise AssertionError("attempt must not run on hot path")

    monkeypatch.setattr("sniper.discord_checker.get_session", lambda: Sess())
    monkeypatch.setattr("sniper.discord_checker.proxy_dict", lambda url: {})

    result = DiscordChecker().check("coolname", "http://user:pass@proxy:1")
    assert result.status == Status.AVAILABLE


def test_discord_429_honors_body_retry_after(monkeypatch):
    def fake_get(url, **kwargs):
        return _FakeResp(
            429,
            {"message": "The resource is being rate limited.", "retry_after": 3.2},
            headers={},
        )

    class Sess:
        def get(self, *a, **k):
            return fake_get(*a, **k)

    monkeypatch.setattr("sniper.discord_checker.get_session", lambda: Sess())
    monkeypatch.setattr("sniper.discord_checker.proxy_dict", lambda url: {})

    result = DiscordChecker().check("coolname", "http://user:pass@proxy:1")
    assert result.status == Status.RATE_LIMITED
    assert result.detail == "retry_after=3.2"

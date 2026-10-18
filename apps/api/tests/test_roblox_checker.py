import json
from unittest.mock import MagicMock

import pytest

from sniper.checkers import roblox_checker
from sniper.checkers.roblox_checker import RobloxChecker, _parse_roblox_body
from sniper.turbo_engine import Status


def test_parse_roblox_available():
    result = _parse_roblox_body("test", 200, json.dumps({"code": 0, "message": "OK"}))
    assert result.status == Status.AVAILABLE


def test_parse_roblox_taken():
    result = _parse_roblox_body(
        "comment", 200, json.dumps({"code": 1, "message": "Username is already in use"})
    )
    assert result.status == Status.TAKEN


def test_roblox_csrf_retry_on_403(monkeypatch):
    checker = RobloxChecker()
    calls: list[dict] = []

    class FakeResp:
        def __init__(self, status_code: int, text: str, headers: dict | None = None):
            self.status_code = status_code
            self.text = text
            self.headers = headers or {}

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return FakeResp(
                403,
                '{"code":0,"message":"Token Validation Failed"}',
                {"x-csrf-token": "abc123"},
            )
        return FakeResp(200, '{"code":1,"message":"Username is already in use"}')

    session = MagicMock()
    session.post = fake_post
    monkeypatch.setattr(roblox_checker, "get_session", lambda: session)

    result = checker.check("comment", "http://proxy:8080")

    assert result.status == Status.TAKEN
    assert len(calls) == 2
    assert calls[1]["headers"]["X-CSRF-TOKEN"] == "abc123"


def test_roblox_uses_cached_csrf(monkeypatch):
    checker = RobloxChecker()
    checker._store_csrf("http://proxy:8080", "cached-token")
    calls: list[dict] = []

    class FakeResp:
        status_code = 200
        text = '{"code":0,"message":"OK"}'
        headers: dict = {}

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        return FakeResp()

    session = MagicMock()
    session.post = fake_post
    monkeypatch.setattr(roblox_checker, "get_session", lambda: session)

    result = checker.check("newname", "http://proxy:8080")

    assert result.status == Status.AVAILABLE
    assert len(calls) == 1
    assert calls[0]["headers"]["X-CSRF-TOKEN"] == "cached-token"

from sniper.checkers.instagram_checker import _from_api_payload, _from_profile_html
from sniper.turbo_engine import Status


def test_ig_api_taken():
    body = '{"data":{"user":{"username":"cristiano"}},"status":"ok"}'
    result = _from_api_payload("cristiano", 200, body)
    assert result is not None
    assert result.status == Status.TAKEN


def test_ig_api_404_available():
    body = '{"message":"User not found","status":"fail"}'
    result = _from_api_payload("freeuser", 404, body)
    assert result is not None
    assert result.status == Status.AVAILABLE


def test_ig_api_html_404_ambiguous():
    assert _from_api_payload("x", 404, "<html>Not Found</html>") is None


def test_ig_page_unavailable():
    body = "<html>Sorry, this page isn't available.</html>"
    result = _from_profile_html("gone", 200, body)
    assert result is not None
    assert result.status == Status.AVAILABLE


def test_ig_page_username_taken():
    body = '{"username":"cristiano","id":"123"}'
    result = _from_profile_html("cristiano", 200, body)
    assert result is not None
    assert result.status == Status.TAKEN

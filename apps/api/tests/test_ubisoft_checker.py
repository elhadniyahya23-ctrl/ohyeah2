from sniper.checkers.ubisoft_checker import classify_ubisoft_validate
from sniper.turbo_engine import Status


def test_ubisoft_available_via_legal_optin():
    body = '{"message":"legalOptinsKey is required"}'
    result = classify_ubisoft_validate("free_name", body, status=400)
    assert result.status == Status.AVAILABLE


def test_ubisoft_taken_via_name_used():
    body = '{"message":"The nameOnPlatform is already used by another player"}'
    result = classify_ubisoft_validate("Beaulo", body, status=400)
    assert result.status == Status.TAKEN


def test_ubisoft_captcha_is_proxy_late():
    body = '{"url":"https://geo.captcha-delivery.com/interstitial/"}'
    result = classify_ubisoft_validate("Beaulo", body, status=403)
    assert result.status == Status.PROXY_LATE


def test_ubisoft_ip_limit_is_rate_limited():
    body = '{"message":"Too many calls per IP address.","httpCode":429}'
    result = classify_ubisoft_validate("Beaulo", body, status=429)
    assert result.status == Status.RATE_LIMITED
    assert "retry_after" in (result.detail or "")


def test_ubisoft_error_field_taken():
    body = '{"errors":{"nameOnPlatform":["already used"]}}'
    result = classify_ubisoft_validate("taken", body, status=400)
    assert result.status == Status.TAKEN

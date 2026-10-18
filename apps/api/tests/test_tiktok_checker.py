from sniper.checkers.tiktok_checker import (
    AVAILABLE_STATUS_CODES,
    TikTokChecker,
    classify_tiktok_html,
    normalize_tiktok_username,
    tiktok_inappropriate_reason,
    tiktok_profile_url,
)
from sniper.turbo_engine import Status


def _universal(user_detail: dict, *, canonical: str | None = None) -> str:
    import json

    scope = {"webapp.user-detail": user_detail}
    if canonical:
        scope["seo.abtest"] = {"canonical": canonical}
    payload = {"__DEFAULT_SCOPE__": scope}
    return (
        '<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">'
        + json.dumps(payload)
        + "</script></html>"
    )


def test_normalize_tiktok_username_from_url():
    assert normalize_tiktok_username("https://www.tiktok.com/@Cool.User") == "cool.user"
    assert normalize_tiktok_username("tiktok.com/@ab") == "ab"
    assert normalize_tiktok_username("@ab") == "ab"
    assert tiktok_profile_url("ab") == "https://www.tiktok.com/@ab"


def test_tiktok_trailing_dot_is_inappropriate():
    assert tiktok_inappropriate_reason("ab.") == "inappropriate"
    assert tiktok_inappropriate_reason("a.") == "inappropriate"
    result = TikTokChecker().check("ab.", "http://user:pass@proxy:1")
    assert result.status == Status.TAKEN
    assert result.detail == "inappropriate"


def test_tiktok_leading_dot_and_underscore_edges_inappropriate():
    assert tiktok_inappropriate_reason(".ab") == "inappropriate"
    assert tiktok_inappropriate_reason("ab_") == "inappropriate"
    assert tiktok_inappropriate_reason("_ab") == "inappropriate"
    assert tiktok_inappropriate_reason("aa..") == "inappropriate"


def test_tiktok_valid_format_ok():
    assert tiktok_inappropriate_reason("ab") is None
    assert tiktok_inappropriate_reason("a.b") is None
    assert tiktok_inappropriate_reason("user_name") is None


def test_tiktok_status_0_is_taken():
    body = _universal(
        {
            "statusCode": 0,
            "userInfo": {"user": {"uniqueId": "charlidamelio"}},
        },
        canonical="https://www.tiktok.com/@charlidamelio",
    )
    result = classify_tiktok_html(
        "charlidamelio",
        body,
        status=200,
        final_url="https://www.tiktok.com/@charlidamelio",
    )
    assert result.status == Status.TAKEN


def test_tiktok_status_10222_with_unique_id_is_taken():
    body = (
        "Couldn't find this account page not available "
        + _universal(
            {
                "statusCode": 10222,
                "userInfo": {"user": {"uniqueId": "lx"}},
            },
            canonical="https://www.tiktok.com/@lx",
        )
    )
    result = classify_tiktok_html("lx", body, status=200, final_url="https://www.tiktok.com/@lx")
    assert result.status == Status.TAKEN


def test_tiktok_i18n_not_found_string_alone_is_not_available():
    body = "<html>Couldn't find this account. Page not available.</html>"
    result = classify_tiktok_html("lx", body, status=200)
    assert result.status != Status.AVAILABLE


def test_tiktok_available_only_10221_empty_msg():
    assert AVAILABLE_STATUS_CODES == {10221}
    body = _universal(
        {"statusCode": 10221, "statusMsg": "", "needFix": False},
        canonical="https://www.tiktok.com/@freeuser",
    )
    result = classify_tiktok_html(
        "freeuser",
        body,
        status=200,
        final_url="https://www.tiktok.com/@freeuser",
    )
    assert result.status == Status.AVAILABLE


def test_tiktok_2c_10221_can_be_available():
    body = _universal(
        {"statusCode": 10221, "statusMsg": "", "needFix": False},
        canonical="https://www.tiktok.com/@qx",
    )
    result = classify_tiktok_html("qx", body, status=200, final_url="https://www.tiktok.com/@qx")
    assert result.status == Status.AVAILABLE


def test_tiktok_4c_10221_can_be_available():
    body = _universal(
        {"statusCode": 10221, "statusMsg": "", "needFix": False},
        canonical="https://www.tiktok.com/@aabl",
    )
    result = classify_tiktok_html("aabl", body, status=200, final_url="https://www.tiktok.com/@aabl")
    assert result.status == Status.AVAILABLE


def test_tiktok_redirect_other_user_is_taken():
    body = _universal(
        {"statusCode": 10221, "statusMsg": "", "needFix": False},
        canonical="https://www.tiktok.com/@other",
    )
    result = classify_tiktok_html(
        "aabl",
        body,
        status=200,
        final_url="https://www.tiktok.com/@other",
    )
    assert result.status == Status.TAKEN
    assert "redirect=" in (result.detail or "")


def test_tiktok_10202_is_not_available():
    body = _universal({"statusCode": 10202, "statusMsg": "", "needFix": False})
    result = classify_tiktok_html("aart", body, status=200, final_url="https://www.tiktok.com/@aart")
    assert result.status == Status.TAKEN
    assert "unclaimable" in (result.detail or "")


def test_tiktok_10221_user_banned_is_taken():
    body = _universal({"statusCode": 10221, "statusMsg": "user banned", "needFix": False})
    result = classify_tiktok_html(
        "coolname",
        body,
        status=200,
        final_url="https://www.tiktok.com/@coolname",
    )
    assert result.status == Status.TAKEN
    assert "banned" in (result.detail or "")


def test_tiktok_10209_is_not_available():
    body = _universal({"statusCode": 10209, "statusMsg": "", "needFix": False})
    result = classify_tiktok_html("tag", body, status=200)
    assert result.status != Status.AVAILABLE


def test_tiktok_available_code_with_user_info_is_taken():
    body = _universal(
        {
            "statusCode": 10221,
            "userInfo": {"user": {"uniqueId": "freeuser"}},
        }
    )
    result = classify_tiktok_html(
        "freeuser",
        body,
        status=200,
        final_url="https://www.tiktok.com/@freeuser",
    )
    assert result.status == Status.TAKEN


def test_tiktok_bare_404_is_not_available():
    result = classify_tiktok_html("nobody", "", status=404)
    assert result.status != Status.AVAILABLE


def test_tiktok_fallback_regex_alone_is_not_available():
    result = classify_tiktok_html("freeuser", '{"statusCode":10221,"statusMsg":""}', status=200)
    assert result.status != Status.AVAILABLE

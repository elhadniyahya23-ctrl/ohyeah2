from sniper.checkers.guns_checker import classify_guns_html
from sniper.turbo_engine import Status


def test_guns_available_requires_default_title_and_not_found():
    body = (
        "<html><h1>Username not found</h1>"
        "<title>guns.lol: Everything you want, right here.</title></html>"
    )
    result = classify_guns_html("cool", body, status=200)
    assert result.status == Status.AVAILABLE


def test_guns_default_title_alone_is_not_available():
    # Proxies often return the marketing shell without a real not-found page.
    body = "<html><title>guns.lol: Everything you want, right here.</title></html>"
    result = classify_guns_html("cool", body, status=200)
    assert result.status != Status.AVAILABLE
    assert result.status == Status.PROXY_LATE


def test_guns_taken_profile_title():
    body = "<html><title>@nike | guns.lol</title><body>profile</body></html>"
    result = classify_guns_html("nike", body, status=200)
    assert result.status == Status.TAKEN


def test_guns_taken_redirect_profile_still_taken():
    # URL /nike serving another handle is still occupied — never a free capture.
    body = "<html><title>@Snoop | guns.lol</title><body>profile</body></html>"
    result = classify_guns_html("nike", body, status=200)
    assert result.status == Status.TAKEN


def test_guns_challenge_not_available():
    body = "<html><title>Just a moment...</title><body>cf-challenge captcha</body></html>"
    result = classify_guns_html("cool", body, status=200)
    assert result.status != Status.AVAILABLE
    assert result.status == Status.PROXY_LATE


def test_guns_generic_profile_html_without_title_is_error():
    body = "<html><body>" + ("x" * 500) + " guns.lol </body></html>"
    result = classify_guns_html("nike", body, status=200)
    assert result.status == Status.PROXY_LATE


def test_guns_bare_404_is_not_available():
    result = classify_guns_html("free", "", status=404)
    assert result.status != Status.AVAILABLE

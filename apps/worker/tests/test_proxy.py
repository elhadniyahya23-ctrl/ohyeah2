import pytest

from worker.engine.proxy import select_proxy_lines, unique_proxy_lines, worker_count


def test_dedupe_proxy_lines():
    lines = ["a:b:c:d", "a:b:c:d", "x:y:1:2", "a:b:c:d"]
    assert unique_proxy_lines(lines) == ["a:b:c:d", "x:y:1:2"]


def test_select_proxy_lines_caps():
    lines = [f"host{i}:8080" for i in range(500)]
    picked = select_proxy_lines(lines, 128)
    assert len(picked) == 128
    assert picked[0] == "host0:8080"
    assert picked[-1] == "host496:8080"


def test_select_proxy_lines_empty():
    assert select_proxy_lines([], 128) == [""]


def test_build_proxy_urls_skips_direct_when_disabled():
    from worker.engine.proxy import build_proxy_urls

    urls = build_proxy_urls(["1.2.3.4:8080"], 128, include_direct_fallback=False)
    assert urls == ["http://1.2.3.4:8080"]


def test_build_proxy_urls_includes_direct_by_default():
    from worker.engine.proxy import build_proxy_urls

    urls = build_proxy_urls(["1.2.3.4:8080"], 128)
    assert urls == ["http://1.2.3.4:8080", None]


def test_proxy_line_password_with_colons():
    from worker.engine.proxy import proxy_line_to_url

    url = proxy_line_to_url("proxy.example.com:8080:user:pass:word:here")
    assert url == "http://user:pass:word:here@proxy.example.com:8080"

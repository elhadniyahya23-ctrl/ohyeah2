import pytest

from worker.engine.proxy import build_proxy_urls


def test_build_proxy_urls_includes_direct():
    urls = build_proxy_urls(["1.2.3.4:8080"], 10)
    assert None in urls
    assert len(urls) >= 2


def test_build_proxy_urls_empty():
    urls = build_proxy_urls([], 10)
    assert urls == [None]

import pytest
import httpx

from worker.platforms.base import CheckOutcome
from worker.platforms.registry import ENDPOINT_CHECKERS, all_platforms, get_checker


@pytest.mark.parametrize("platform", all_platforms())
def test_registry_has_checker(platform: str):
    assert get_checker(platform) is not None
    assert get_checker(platform).platform == platform


@pytest.mark.asyncio
async def test_telegram_taken():
    checker = ENDPOINT_CHECKERS["telegram"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='<div class="tgme_page_photo"></div>')

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await checker.check(client, "durov")

    assert result.outcome == CheckOutcome.TAKEN


@pytest.mark.asyncio
async def test_telegram_available():
    checker = ENDPOINT_CHECKERS["telegram"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="If you have Telegram, you can contact @name")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await checker.check(client, "free_name")

    assert result.outcome == CheckOutcome.AVAILABLE


@pytest.mark.asyncio
async def test_whatsapp_available_and_taken():
    checker = ENDPOINT_CHECKERS["whatsapp"]

    def available(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    def taken(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    async with httpx.AsyncClient(transport=httpx.MockTransport(available)) as client:
        assert (await checker.check(client, "free")).outcome == CheckOutcome.AVAILABLE

    async with httpx.AsyncClient(transport=httpx.MockTransport(taken)) as client:
        assert (await checker.check(client, "john")).outcome == CheckOutcome.TAKEN


@pytest.mark.asyncio
async def test_guns_title_parsing():
    checker = ENDPOINT_CHECKERS["guns"]

    def taken(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<title>@cool | guns.lol</title>")

    def available(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<title>guns.lol: Everything you want, right here.</title>",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(taken)) as client:
        assert (await checker.check(client, "cool")).outcome == CheckOutcome.TAKEN

    async with httpx.AsyncClient(transport=httpx.MockTransport(available)) as client:
        assert (await checker.check(client, "cool")).outcome == CheckOutcome.AVAILABLE


@pytest.mark.asyncio
async def test_tiktok_status_code():
    checker = ENDPOINT_CHECKERS["tiktok"]

    def taken(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">'
                '{"__DEFAULT_SCOPE__":{"webapp.user-detail":{"statusCode":0,'
                '"userInfo":{"user":{"uniqueId":"user"}}}}}'
                "</script></html>"
            ),
        )

    def available(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">'
                '{"__DEFAULT_SCOPE__":{"webapp.user-detail":{"statusCode":10221,"statusMsg":""}}}'
                "</script></html>"
            ),
        )

    def ghost_10202(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">'
                '{"__DEFAULT_SCOPE__":{"webapp.user-detail":{"statusCode":10202,"statusMsg":""}}}'
                "</script></html>"
            ),
        )

    def banned(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">'
                '{"__DEFAULT_SCOPE__":{"webapp.user-detail":{"statusCode":10221,"statusMsg":"user banned"}}}'
                "</script></html>"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(taken)) as client:
        assert (await checker.check(client, "user")).outcome == CheckOutcome.TAKEN

    async with httpx.AsyncClient(transport=httpx.MockTransport(available)) as client:
        assert (await checker.check(client, "freeuser")).outcome == CheckOutcome.AVAILABLE

    async with httpx.AsyncClient(transport=httpx.MockTransport(available)) as client:
        assert (await checker.check(client, "ab")).outcome == CheckOutcome.AVAILABLE

    async with httpx.AsyncClient(transport=httpx.MockTransport(ghost_10202)) as client:
        assert (await checker.check(client, "aart")).outcome == CheckOutcome.TAKEN

    async with httpx.AsyncClient(transport=httpx.MockTransport(banned)) as client:
        assert (await checker.check(client, "coolname")).outcome == CheckOutcome.TAKEN


@pytest.mark.asyncio
async def test_ubisoft_available_via_validatecreation():
    checker = ENDPOINT_CHECKERS["ubisoft"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "public-ubiservices.ubi.com"
        return httpx.Response(
            400,
            json={"message": "legalOptinsKey is required"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await checker.check(client, "free_name")

    assert result.outcome == CheckOutcome.AVAILABLE


@pytest.mark.asyncio
async def test_ubisoft_taken_via_validatecreation():
    checker = ENDPOINT_CHECKERS["ubisoft"]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"message": "The nameOnPlatform is already used by another player"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await checker.check(client, "taken")

    assert result.outcome == CheckOutcome.TAKEN


@pytest.mark.asyncio
async def test_ubisoft_captcha_is_rate_limited():
    checker = ENDPOINT_CHECKERS["ubisoft"]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"url": "https://geo.captcha-delivery.com/interstitial/"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await checker.check(client, "test")

    assert result.outcome == CheckOutcome.RATE_LIMITED


@pytest.mark.asyncio
async def test_discord_attempt_post_parsing():
    checker = ENDPOINT_CHECKERS["discord"]

    def taken(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("username-attempt-unauthed")
        return httpx.Response(200, json={"taken": True})

    def available(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"taken": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(taken)) as client:
        assert (await checker.check(client, "taken")).outcome == CheckOutcome.TAKEN

    async with httpx.AsyncClient(transport=httpx.MockTransport(available)) as client:
        assert (await checker.check(client, "free")).outcome == CheckOutcome.AVAILABLE


@pytest.mark.asyncio
async def test_discord_400_invalid_username_is_taken():
    from worker.platforms.discord import parse_attempt_response

    result = parse_attempt_response("bad!!", 400, '{"code":50035,"message":"Invalid username"}')
    assert result.outcome == CheckOutcome.TAKEN


@pytest.mark.asyncio
async def test_discord_400_unknown_is_error():
    from worker.platforms.discord import parse_attempt_response

    result = parse_attempt_response("x", 400, '{"message":"something else"}')
    assert result.outcome == CheckOutcome.ERROR


@pytest.mark.asyncio
async def test_discord_403_is_rate_limited():
    checker = ENDPOINT_CHECKERS["discord"]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Unauthorized", "code": 0})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await checker.check(client, "test")

    assert result.outcome == CheckOutcome.RATE_LIMITED


@pytest.mark.asyncio
async def test_discord_rate_limit_message_is_rate_limited():
    checker = ENDPOINT_CHECKERS["discord"]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": "The resource is being rate limited.", "retry_after": 1.5},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await checker.check(client, "test")

    assert result.outcome == CheckOutcome.RATE_LIMITED


@pytest.mark.asyncio
async def test_epic_cloudflare_is_rate_limited():
    checker = ENDPOINT_CHECKERS["epic"]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="<html>Just a moment...</html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await checker.check(client, "test")

    assert result.outcome == CheckOutcome.RATE_LIMITED

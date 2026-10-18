from sniper.checkers.minecraft_checker import (
    MinecraftChecker,
    _mojang_available_body,
    _mojang_taken_body,
    minecraft_inappropriate_reason,
)
from sniper.turbo_engine import Status


def test_mojang_taken_requires_profile_json():
    assert _mojang_taken_body(200, '{"id":"abc","name":"Notch"}') is True
    assert _mojang_taken_body(200, "{}") is False
    assert _mojang_taken_body(404, '{"id":"abc"}') is False


def test_mojang_available_rejects_html_404():
    assert _mojang_available_body(404, "<html>Not Found</html>") is False
    assert _mojang_available_body(404, "") is False


def test_mojang_available_accepts_error_payload():
    body = '{"path":"/users/profiles/minecraft/ref","errorMessage":"Couldn\'t find any profile with name ref"}'
    assert _mojang_available_body(404, body) is True
    assert _mojang_available_body(204, "") is True


def test_mojang_available_rejects_profile_shaped_404():
    assert _mojang_available_body(404, '{"id":"abc","name":"ref"}') is False


def test_minecraft_insults_are_inappropriate():
    assert minecraft_inappropriate_reason("fuck") == "inappropriate"
    assert minecraft_inappropriate_reason("FuCk") == "inappropriate"
    assert minecraft_inappropriate_reason("shit99") == "inappropriate"
    assert minecraft_inappropriate_reason("xxxshit") == "inappropriate"
    assert minecraft_inappropriate_reason("salope") == "inappropriate"
    assert minecraft_inappropriate_reason("asshole1") == "inappropriate"


def test_minecraft_abbreviations_en_fr():
    for name in (
        "fdp",
        "fdp69",
        "ntm",
        "ntm123",
        "ptn",
        "ptn99",
        "pt1",
        "put1",
        "vtf",
        "vtfe",
        "vtff",
        "tg69",
        "ftg",
        "fpc",
        "tmlp",
        "tdc",
        "blc",
        "pdm",
        "stfu",
        "gtfo",
        "kys",
        "kms",
        "fck",
        "fuk",
        "sht",
        "btch",
        "azz",
        "ffs",
        "fml",
        "omfg",
        "idgaf",
        "sob",
        "pos",
        "dtf",
        "thot",
        "nsfw",
        "fafo",
        "mofo",
        "n1gger",
        "b1tch",
        "a55",
        "c0nnard",
        "sh1t",
        "fvck",
    ):
        assert minecraft_inappropriate_reason(name) == "inappropriate", name


def test_minecraft_false_positives_allowed():
    for name in (
        "unique",
        "Unique1",
        "technique",
        "torpedo",
        "assassin",
        "classy",
        "computer",
        "dispute",
        "xxxxzz99",
        "Steve",
        "grape",
        "cockpit",
        "ftw",
        "tgv",
        "osef",
        "mdr",
        "lmao",
    ):
        assert minecraft_inappropriate_reason(name) is None, name


def test_minecraft_invalid_format():
    assert minecraft_inappropriate_reason("a") == "invalid"
    assert minecraft_inappropriate_reason("hello-world") == "invalid"
    assert minecraft_inappropriate_reason("thisnameistoolong1") == "invalid"


def test_minecraft_checker_skips_http_for_insults():
    result = MinecraftChecker().check("fuck", "")
    assert result.status == Status.TAKEN
    assert result.detail == "inappropriate"

from services.name_generator import MAX_STACK_LAYERS, merge_names


def test_merge_append_puts_newest_first():
    merged = merge_names(["aa", "ab", "ac"], ["xx", "xy"], append=True)
    assert merged[:2] == ["xx", "xy"]
    assert "aa" in merged
    assert len(merged) == 5


def test_merge_append_dedupes_keeping_newest():
    merged = merge_names(["aa", "bb"], ["bb", "cc"], append=True)
    assert merged == ["bb", "cc", "aa"]


def test_merge_replace():
    merged = merge_names(["aa", "bb"], ["xx"], append=False)
    assert merged == ["xx"]


def test_stack_limit_constant():
    assert MAX_STACK_LAYERS == 10

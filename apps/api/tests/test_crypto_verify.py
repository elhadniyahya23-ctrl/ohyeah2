from services.crypto_verify import VerifyResult, _amount_ok


def test_amount_ok_within_tolerance():
    assert _amount_ok(9.0, 9.99) is True
    assert _amount_ok(8.8, 9.99) is True
    assert _amount_ok(5.0, 9.99) is False


def test_amount_ok_exact():
    assert _amount_ok(2.99, 2.99) is True


def test_verify_result_defaults():
    r = VerifyResult(False, "pending", "wait")
    assert r.ok is False
    assert r.status == "pending"

from services.signup_guard import normalize_ip


def test_normalize_ip_strips_mapped():
    assert normalize_ip("::ffff:1.2.3.4") == "1.2.3.4"
    assert normalize_ip(" 8.8.8.8 ") == "8.8.8.8"

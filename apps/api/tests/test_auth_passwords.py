from werkzeug.security import generate_password_hash

from services.auth import hash_password, is_legacy_password_hash, verify_password


def test_hash_and_verify_bcrypt_roundtrip():
    hashed = hash_password("secret123")
    assert hashed.startswith("$2")
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_legacy_werkzeug_scrypt():
    legacy = generate_password_hash("oldpass99")
    assert is_legacy_password_hash(legacy)
    assert verify_password("oldpass99", legacy)
    assert not verify_password("nope", legacy)


def test_verify_legacy_werkzeug_pbkdf2():
    legacy = generate_password_hash("oldpass99", method="pbkdf2:sha256")
    assert verify_password("oldpass99", legacy)
    assert not verify_password("nope", legacy)

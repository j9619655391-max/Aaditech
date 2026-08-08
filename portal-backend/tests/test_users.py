"""
Tests for the local portal account store (app/users.py) — the bootstrap
admin created by the one-click setup wizard.
"""
import pytest

from app import users


@pytest.fixture(autouse=True)
def _fresh_db():
    users.init_db("")  # in-memory, reset per test
    yield


def test_create_and_verify_credentials():
    user = users.create_user("admin", "correct-horse-battery", ["viewer", "support_engineer"])
    assert user["username"] == "admin"
    assert "cleanup_approver" not in user["roles"]

    ok = users.verify_credentials("admin", "correct-horse-battery")
    assert ok and ok["username"] == "admin" and "support_engineer" in ok["roles"]

    assert users.verify_credentials("admin", "wrong-password") is None
    assert users.verify_credentials("nobody", "whatever123") is None


def test_password_stored_hashed_not_plaintext():
    users.create_user("secure", "super-secret-123", ["viewer"])
    row = users.get_user("secure")
    assert row["password_hash"] != "super-secret-123"
    assert "$2b$" in row["password_hash"]  # bcrypt


def test_duplicate_username_rejected():
    users.create_user("dup", "password123", ["viewer"])
    with pytest.raises(ValueError):
        users.create_user("dup", "other-password", ["viewer"])


def test_short_password_rejected():
    with pytest.raises(ValueError):
        users.create_user("shorty", "tiny", ["viewer"])

"""Unit tests for the JWT auth module. Run with: pytest tests/test_auth.py"""
import pytest
from fastapi import HTTPException

from app.auth import create_access_token, decode_access_token


def test_create_and_decode_token_roundtrip():
    token = create_access_token(subject="jdoe", roles=["engineer"])
    payload = decode_access_token(token)

    assert payload["sub"] == "jdoe"
    assert payload["roles"] == ["engineer"]


def test_decode_invalid_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not-a-real-token")

    assert exc_info.value.status_code == 401


def test_decode_tampered_token_raises_401():
    token = create_access_token(subject="jdoe", roles=["engineer"])
    tampered = token[:-4] + "abcd"

    with pytest.raises(HTTPException):
        decode_access_token(tampered)

from datetime import timedelta
import pytest
from app.core.exceptions import AuthenticationError
from app.core.security import (
    compute_payload_hash,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
    verify_payload_hash,
)


def test_password_hashing():
    raw_password = "SuperSecretPassword123!"
    hashed = hash_password(raw_password)

    assert hashed != raw_password
    assert hashed.startswith("$argon2")
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_jwt_create_and_decode():
    token = create_access_token(
        subject="user-12345",
        email="test@example.com",
        role="EMPLOYEE",
        expires_delta=timedelta(minutes=15),
    )
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload["sub"] == "user-12345"
    assert payload["email"] == "test@example.com"
    assert payload["role"] == "EMPLOYEE"


def test_jwt_expired_token():
    # Token expired 1 minute ago
    token = create_access_token(
        subject="user-12345",
        email="test@example.com",
        role="EMPLOYEE",
        expires_delta=timedelta(minutes=-1),
    )

    with pytest.raises(AuthenticationError) as exc_info:
        decode_access_token(token)
    assert "expired" in str(exc_info.value).lower()


def test_jwt_tampered_token():
    token = create_access_token(
        subject="user-12345",
        email="test@example.com",
        role="EMPLOYEE",
    )
    tampered_token = token[:-5] + "abcde"

    with pytest.raises(AuthenticationError) as exc_info:
        decode_access_token(tampered_token)
    assert "invalid" in str(exc_info.value).lower()


def test_refresh_token_generation_and_hashing():
    raw_token, token_hash = generate_refresh_token()

    assert len(raw_token) > 20
    assert len(token_hash) == 64  # SHA-256 hex length
    assert hash_token(raw_token) == token_hash
    assert hash_token("different_raw_token") != token_hash


def test_payload_hash_verification():
    payload = {"card_id": "abc1234", "list_id": "xyz9876", "title": "Deploy update"}
    payload_hash = compute_payload_hash(payload)

    assert len(payload_hash) == 64
    assert verify_payload_hash(payload, payload_hash) is True
    assert verify_payload_hash({"card_id": "different"}, payload_hash) is False


import pytest
from app.core.config import Settings, settings
from app.core.security import compute_payload_hash, verify_payload_hash


def test_settings_load_defaults():
    assert settings.PROJECT_NAME == "Agentic Task Manager"
    assert settings.API_V1_STR == "/api/v1"
    assert isinstance(settings.BACKEND_CORS_ORIGINS, list)
    assert len(settings.BACKEND_CORS_ORIGINS) > 0


def test_cors_origins_validator():
    s = Settings(BACKEND_CORS_ORIGINS="http://example.com, https://example.org")
    assert s.BACKEND_CORS_ORIGINS == ["http://example.com", "https://example.org"]


def test_security_payload_hashing():
    payload_a = {"card_id": "123", "action": "MOVE", "target_list": "DONE"}
    payload_b = {"target_list": "DONE", "action": "MOVE", "card_id": "123"}
    payload_c = {"card_id": "123", "action": "MOVE", "target_list": "TODO"}

    hash_a = compute_payload_hash(payload_a)
    hash_b = compute_payload_hash(payload_b)
    hash_c = compute_payload_hash(payload_c)

    # Key ordering shouldn't change the hash
    assert hash_a == hash_b
    assert verify_payload_hash(payload_a, hash_a)
    assert verify_payload_hash(payload_b, hash_a)

    # Different payload must produce different hash
    assert hash_a != hash_c
    assert not verify_payload_hash(payload_c, hash_a)


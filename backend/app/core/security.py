import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from app.core.config import settings
from app.core.exceptions import AuthenticationError

# Argon2 Password Hasher instance with recommended parameters
_password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


# --- Phase 1 Payload Hashing for Pending Actions (Preserved) ---
def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """
    Computes a deterministic SHA-256 hash of a payload dictionary.
    Keys are sorted to guarantee reproducibility.
    """
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def verify_payload_hash(payload: Dict[str, Any], expected_hash: str) -> bool:
    """Verifies that payload matches the expected hash."""
    return compute_payload_hash(payload) == expected_hash


# --- Phase 3 Argon2 Password Hashing ---
def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2."""
    if not password:
        raise ValueError("Password cannot be empty.")
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2 hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# --- Phase 3 JWT Token Management ---
def create_access_token(
    subject: str,
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Creates a signed JWT access token.
    Contains: sub (user_id), email, role, iat, exp.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": str(subject),
        "email": email,
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT access token.
    Raises AuthenticationError if expired or invalid signature.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "role", "email"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Access token has expired.")
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(f"Invalid access token: {exc}")


# --- Phase 3 Refresh Token Hashing & Rotation ---
def hash_token(raw_token: str) -> str:
    """Compute a SHA-256 hash of a refresh token to safely store in MongoDB."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_refresh_token() -> tuple[str, str]:
    """
    Generates a cryptographically strong refresh token.
    Returns:
        (raw_token_for_client, hashed_token_for_storage)
    """
    raw_token = secrets.token_urlsafe(48)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash

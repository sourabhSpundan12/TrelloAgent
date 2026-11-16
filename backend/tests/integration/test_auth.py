import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_registration_and_login_flow(test_client: AsyncClient):
    # 1. Register a new user
    register_payload = {
        "email": "sarah.connor@example.com",
        "password": "Password123!",
        "full_name": "Sarah Connor",
        "role": "EMPLOYEE",
        "department": "Security Operations",
    }
    reg_resp = await test_client.post("/api/v1/auth/register", json=register_payload)
    assert reg_resp.status_code == 201
    user_data = reg_resp.json()
    assert user_data["email"] == "sarah.connor@example.com"
    assert user_data["full_name"] == "Sarah Connor"
    assert user_data["role"] == "EMPLOYEE"
    assert "hashed_password" not in user_data
    assert "password" not in user_data

    # 2. Prevent duplicate email registration
    dup_resp = await test_client.post("/api/v1/auth/register", json=register_payload)
    assert dup_resp.status_code == 409
    dup_data = dup_resp.json()
    assert dup_data["error"]["code"] == "RESOURCE_CONFLICT"

    # 3. Successful Login
    login_resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "sarah.connor@example.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"

    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]

    # 4. Get Current User /me
    me_resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "sarah.connor@example.com"
    assert me_data["id"] == user_data["id"]

    # 5. Rotate Refresh Token
    refresh_resp = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    new_token_data = refresh_resp.json()
    assert new_token_data["access_token"] != access_token
    assert new_token_data["refresh_token"] != refresh_token

    # 6. Attempt reuse of old refresh token (should fail)
    reuse_resp = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert reuse_resp.status_code == 401
    assert reuse_resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_auth_invalid_credentials(test_client: AsyncClient):
    # Non-existent user
    resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "Password123!"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"

    # Register user then provide wrong password
    await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "kyle.reese@example.com",
            "password": "CorrectPassword123!",
            "full_name": "Kyle Reese",
            "role": "EMPLOYEE",
        },
    )

    bad_pw_resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "kyle.reese@example.com", "password": "IncorrectPassword!"},
    )
    assert bad_pw_resp.status_code == 401
    assert bad_pw_resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_auth_unauthorized_access(test_client: AsyncClient):
    # Missing Authorization header
    resp = await test_client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"

    # Invalid token format
    resp2 = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert resp2.status_code == 401
    assert resp2.json()["error"]["code"] == "AUTHENTICATION_FAILED"


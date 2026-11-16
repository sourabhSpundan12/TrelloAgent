import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_users_endpoints_and_rbac(test_client: AsyncClient):
    # 1. Register Admin user
    admin_reg = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@example.com",
            "password": "AdminPassword123!",
            "full_name": "Admin User",
            "role": "ADMIN",
            "department": "IT",
        },
    )
    assert admin_reg.status_code == 201

    admin_login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminPassword123!"},
    )
    admin_token = admin_login.json()["access_token"]

    # 2. Register Employee user
    emp_reg = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "emp@example.com",
            "password": "EmployeePassword123!",
            "full_name": "Employee User",
            "role": "EMPLOYEE",
            "department": "Engineering",
        },
    )
    assert emp_reg.status_code == 201

    emp_login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "emp@example.com", "password": "EmployeePassword123!"},
    )
    emp_token = emp_login.json()["access_token"]

    # 3. Employee accessing GET /users/me
    emp_me = await test_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert emp_me.status_code == 200
    assert emp_me.json()["email"] == "emp@example.com"

    # 4. Employee updating their profile PATCH /users/me
    update_resp = await test_client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {emp_token}"},
        json={"full_name": "Employee Updated", "department": "Core Platform"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["full_name"] == "Employee Updated"
    assert update_resp.json()["department"] == "Core Platform"

    # 5. RBAC: Employee attempting to access restricted GET /users (Should be 403 Forbidden)
    emp_list_resp = await test_client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert emp_list_resp.status_code == 403
    assert emp_list_resp.json()["error"]["code"] == "PERMISSION_DENIED"

    # 6. RBAC: Admin accessing restricted GET /users (Should be 200 OK)
    admin_list_resp = await test_client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_list_resp.status_code == 200
    list_data = admin_list_resp.json()
    assert "users" in list_data
    assert list_data["total"] >= 2
    assert any(u["email"] == "admin@example.com" for u in list_data["users"])
    assert any(u["email"] == "emp@example.com" for u in list_data["users"])


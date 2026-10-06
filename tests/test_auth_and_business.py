import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_auth_and_business_flow():
    unique_id = uuid.uuid4().hex[:8]
    email = f"user_{unique_id}@example.com"
    password = "Password123!"
    name = f"Test User {unique_id}"

    # 1. Sign Up (FEAT-01)
    signup_res = client.post(
        "/auth/signup",
        json={"name": name, "email": email, "password": password},
    )
    assert signup_res.status_code == 201, signup_res.text
    signup_data = signup_res.json()
    assert "access_token" in signup_data
    assert signup_data["token_type"] == "bearer"
    assert signup_data["user"]["email"] == email
    assert signup_data["user"]["name"] == name
    assert "id" in signup_data["user"]
    token = signup_data["access_token"]

    # Duplicate email fails
    dup_res = client.post(
        "/auth/signup",
        json={"name": name, "email": email, "password": password},
    )
    assert dup_res.status_code == 409

    # 2. Sign In (FEAT-02)
    login_res = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200, login_res.text
    login_data = login_res.json()
    assert "access_token" in login_data

    # Bad password fails
    bad_login = client.post(
        "/auth/login",
        json={"email": email, "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401

    # 3. Current User Profile
    auth_headers = {"Authorization": f"Bearer {token}"}
    me_res = client.get("/auth/me", headers=auth_headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email

    # 4. Sign Out (FEAT-03)
    logout_res = client.post("/auth/logout", headers=auth_headers)
    assert logout_res.status_code == 200

    # 5. Create Business (FEAT-06)
    biz_res = client.post(
        "/businesses",
        json={"name": f"Shop {unique_id}", "business_type": "Retail"},
        headers=auth_headers,
    )
    assert biz_res.status_code == 201, biz_res.text
    biz_data = biz_res.json()
    biz_id = biz_data["id"]
    assert biz_data["name"] == f"Shop {unique_id}"
    assert biz_data["business_type"] == "Retail"

    # 6. List My Businesses (FEAT-07)
    mine_res = client.get("/businesses/mine", headers=auth_headers)
    assert mine_res.status_code == 200, mine_res.text
    mine_data = mine_res.json()
    assert isinstance(mine_data, list)
    matching = [b for b in mine_data if b["id"] == biz_id]
    assert len(matching) == 1
    assert matching[0]["role"] == "owner"
    assert matching[0]["can_edit"] is True
    assert matching[0]["can_delete"] is True

    # 7. Password Reset flow (FEAT-05)
    req_reset = client.post(
        "/auth/request-reset",
        json={"email": email},
    )
    assert req_reset.status_code == 200
    reset_token = req_reset.json().get("reset_token")
    assert reset_token is not None

    new_password = "NewPassword123!"
    confirm_reset = client.post(
        "/auth/confirm-reset",
        json={"token": reset_token, "new_password": new_password},
    )
    assert confirm_reset.status_code == 200

    # Login with new password
    login_new = client.post(
        "/auth/login",
        json={"email": email, "password": new_password},
    )
    assert login_new.status_code == 200

    # 8. Business Scoping Rule (FEAT-08)
    # Missing X-Business-Id -> 400
    res_no_header = client.get("/businesses/current", headers=auth_headers)
    assert res_no_header.status_code == 400, res_no_header.text

    # Invalid / unjoined business_id -> 403
    fake_biz_id = "00000000-0000-0000-0000-000000000000"
    res_forbidden = client.get(
        "/businesses/current",
        headers={**auth_headers, "X-Business-Id": fake_biz_id},
    )
    assert res_forbidden.status_code == 403

    # Valid business_id -> 200 with membership
    res_valid_scope = client.get(
        "/businesses/current",
        headers={**auth_headers, "X-Business-Id": biz_id},
    )
    assert res_valid_scope.status_code == 200
    scope_data = res_valid_scope.json()
    assert scope_data["business_id"] == biz_id
    assert scope_data["role"] == "owner"

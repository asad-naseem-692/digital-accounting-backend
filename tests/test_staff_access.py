import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_staff_access_management_flow():
    uid = uuid.uuid4().hex[:8]
    owner_email = f"owner_{uid}@example.com"
    owner_pass = "OwnerPass123!"

    # 1. Register owner
    res = client.post("/auth/signup", json={"name": "Shop Owner", "email": owner_email, "password": owner_pass})
    assert res.status_code == 201
    owner_token = res.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 2. Create business
    res = client.post("/businesses", json={"name": f"Mart {uid}", "business_type": "Retail"}, headers=owner_headers)
    assert res.status_code == 201
    biz_id = res.json()["id"]
    owner_headers["X-Business-Id"] = biz_id

    # 3. List staff members initially (should contain only the owner)
    res = client.get(f"/businesses/{biz_id}/staff", headers=owner_headers)
    assert res.status_code == 200
    members = res.json()
    assert len(members) == 1
    assert members[0]["role"] == "owner"
    assert members[0]["can_edit"] is True
    assert members[0]["can_delete"] is True

    # 4. Invite staff member with View Only rights (can_edit=False, can_delete=False)
    staff_email = f"staff_{uid}@example.com"
    staff_pass = "StaffPass123!"
    res = client.post(
        f"/businesses/{biz_id}/staff",
        json={
            "name": "Audit Staff",
            "email": staff_email,
            "password": staff_pass,
            "can_edit": False,
            "can_delete": False,
        },
        headers=owner_headers,
    )
    assert res.status_code == 201
    staff_member = res.json()
    assert staff_member["name"] == "Audit Staff"
    assert staff_member["email"] == staff_email
    assert staff_member["role"] == "staff"
    assert staff_member["can_edit"] is False
    assert staff_member["can_delete"] is False
    staff_user_id = staff_member["user_id"]

    # 5. Verify staff list has 2 members now
    res = client.get(f"/businesses/{biz_id}/staff", headers=owner_headers)
    assert res.status_code == 200
    members = res.json()
    assert len(members) == 2

    # 6. Staff member logs in and tries to create a party (should fail because can_edit is False)
    staff_login = client.post("/auth/login", json={"email": staff_email, "password": staff_pass})
    assert staff_login.status_code == 200
    staff_token = staff_login.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}", "X-Business-Id": biz_id}

    # Staff tries to add party -> should be blocked with 403 (require_can_edit)
    res = client.post("/parties", json={"name": "Customer X", "type": "customer"}, headers=staff_headers)
    assert res.status_code == 403

    # Staff tries to manage staff -> should be blocked with 403 (only owner allowed)
    res = client.get(f"/businesses/{biz_id}/staff", headers=staff_headers)
    assert res.status_code == 403

    # 7. Owner upgrades staff to Editor (can_edit=True, can_delete=False)
    res = client.patch(
        f"/businesses/{biz_id}/staff/{staff_user_id}",
        json={"can_edit": True, "can_delete": False},
        headers=owner_headers,
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["can_edit"] is True
    assert updated["can_delete"] is False

    # 8. Now staff can create a party!
    res = client.post("/parties", json={"name": "Customer Y", "type": "customer"}, headers=staff_headers)
    assert res.status_code == 201
    party_id = res.json()["id"]

    # 9. But staff CANNOT delete (require_can_delete)
    # Owner removes staff member
    res = client.delete(f"/businesses/{biz_id}/staff/{staff_user_id}", headers=owner_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # Staff member user account is revoked and deleted -> token invalid
    res = client.get("/parties", headers=staff_headers)
    assert res.status_code == 401

    # Staff member can NEVER log in again with those credentials
    relogin = client.post("/auth/login", json={"email": staff_email, "password": staff_pass})
    assert relogin.status_code == 401


def test_staff_supplier_payment_restriction_and_business_creation():
    uid = uuid.uuid4().hex[:8]
    owner_email = f"owner2_{uid}@example.com"
    owner_pass = "OwnerPass123!"

    # 1. Register owner & create business
    res = client.post("/auth/signup", json={"name": "Shop Owner 2", "email": owner_email, "password": owner_pass})
    owner_token = res.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    res = client.post("/businesses", json={"name": f"Store {uid}", "business_type": "Retail"}, headers=owner_headers)
    biz_id = res.json()["id"]
    owner_headers["X-Business-Id"] = biz_id

    # 2. Create supplier party
    res = client.post("/parties", json={"name": "Wholesaler A", "type": "supplier"}, headers=owner_headers)
    assert res.status_code == 201
    supplier_id = res.json()["id"]

    # 3. Create staff member with Editor permissions (can_edit=True)
    staff_email = f"cashier_{uid}@example.com"
    staff_pass = "CashierPass123!"
    res = client.post(
        f"/businesses/{biz_id}/staff",
        json={"name": "Cashier", "email": staff_email, "password": staff_pass, "can_edit": True, "can_delete": False},
        headers=owner_headers,
    )
    assert res.status_code == 201

    # Login as cashier
    res = client.post("/auth/login", json={"email": staff_email, "password": staff_pass})
    assert res.status_code == 200
    staff_token = res.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}", "X-Business-Id": biz_id}

    # 4. Cashier attempts to create a business -> BLOCKED with 403
    res = client.post("/businesses", json={"name": "Illegal Branch", "business_type": "Retail"}, headers=staff_headers)
    assert res.status_code == 403
    assert "Staff accounts are not permitted" in res.json()["detail"]

    # 5. Cashier can record expense
    res = client.post(
        "/transactions",
        json={
            "transaction_type": "expense",
            "amount": 200.0,
            "category": "Chai & Refreshments",
            "description": "Counter tea expense",
            "payment_mode": "cash",
        },
        headers=staff_headers,
    )
    assert res.status_code == 201

    # 6. Cashier attempts to Pay Supplier (payment_money) -> BLOCKED with 403
    res = client.post(
        "/transactions",
        json={
            "transaction_type": "payment_money",
            "party_id": supplier_id,
            "amount": 5000.0,
            "description": "Paying wholesaler debt",
            "payment_mode": "cash",
        },
        headers=staff_headers,
    )
    assert res.status_code == 403
    assert "Supplier payments are restricted to the Business Owner only" in res.json()["detail"]

    # 7. Cashier attempts to record debit on supplier ledger -> BLOCKED with 403
    res = client.post(
        f"/parties/{supplier_id}/transactions",
        json={
            "type": "debit",
            "amount": 5000.0,
            "description": "Direct debit to supplier",
        },
        headers=staff_headers,
    )
    assert res.status_code == 403
    assert "Supplier payments are restricted to the Business Owner only" in res.json()["detail"]

    # 8. Owner CAN Pay Supplier (payment_money)
    res = client.post(
        "/transactions",
        json={
            "transaction_type": "payment_money",
            "party_id": supplier_id,
            "amount": 5000.0,
            "description": "Owner paying wholesaler",
            "payment_mode": "cash",
        },
        headers=owner_headers,
    )
    assert res.status_code == 201

    # 9. Cashier attempts to create a Purchase Bill -> BLOCKED with 403
    res = client.post(
        "/invoices",
        json={
            "invoice_type": "purchase",
            "party_id": supplier_id,
            "items": [{"description": "Raw goods", "quantity": 10, "unit_price": 500.0}],
        },
        headers=staff_headers,
    )
    assert res.status_code == 403
    assert "Purchase bills can only be created by the Business Owner" in res.json()["detail"]

    # 10. Owner creates a Purchase Bill -> SUCCESS
    res = client.post(
        "/invoices",
        json={
            "invoice_type": "purchase",
            "party_id": supplier_id,
            "items": [{"description": "Raw goods", "quantity": 10, "unit_price": 500.0}],
        },
        headers=owner_headers,
    )
    assert res.status_code == 201
    purchase_bill_id = res.json()["id"]

    # 11. Customer party
    res = client.post("/parties", json={"name": "Retail Customer", "type": "customer"}, headers=owner_headers)
    assert res.status_code == 201
    customer_id = res.json()["id"]

    # 12. Cashier creates a Sales Invoice -> SUCCESS
    res = client.post(
        "/invoices",
        json={
            "invoice_type": "sale",
            "party_id": customer_id,
            "items": [{"description": "Sold Item", "quantity": 2, "unit_price": 1000.0}],
        },
        headers=staff_headers,
    )
    assert res.status_code == 201
    sale_inv_id = res.json()["id"]

    # 13. Cashier lists invoices -> ONLY sees sale invoices, NOT purchase bills
    res = client.get("/invoices", headers=staff_headers)
    assert res.status_code == 200
    staff_invs = res.json()
    assert all(inv["invoice_type"] == "sale" for inv in staff_invs)
    assert any(inv["id"] == sale_inv_id for inv in staff_invs)
    assert not any(inv["id"] == purchase_bill_id for inv in staff_invs)

    # 14. Cashier tries to directly view or download purchase bill -> 403 Forbidden
    res = client.get(f"/invoices/{purchase_bill_id}", headers=staff_headers)
    assert res.status_code == 403

    res = client.get(f"/invoices/{purchase_bill_id}/pdf", headers=staff_headers)
    assert res.status_code == 403

    # 15. Owner can view both
    res = client.get(f"/invoices/{purchase_bill_id}", headers=owner_headers)
    assert res.status_code == 200
    res = client.get(f"/invoices/{sale_inv_id}", headers=owner_headers)
    assert res.status_code == 200



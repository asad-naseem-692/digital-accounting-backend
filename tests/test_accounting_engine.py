import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_full_accounting_workflow():
    uid = uuid.uuid4().hex[:8]
    email = f"accountant_{uid}@example.com"
    password = "Password123!"

    # 1. Sign up & get token
    signup_res = client.post(
        "/auth/signup",
        json={"name": f"Accountant {uid}", "email": email, "password": password},
    )
    assert signup_res.status_code == 201
    token = signup_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Business
    biz_res = client.post(
        "/businesses",
        json={"name": f"Enterprise {uid}", "business_type": "Wholesale"},
        headers=auth_headers,
    )
    assert biz_res.status_code == 201
    biz_id = biz_res.json()["id"]
    headers = {**auth_headers, "X-Business-Id": biz_id}

    # 3. Create Customer with opening balance $100 (they owe us)
    cust_res = client.post(
        "/parties",
        json={
            "name": f"Customer One {uid}",
            "type": "customer",
            "phone": "555-0101",
            "opening_balance": 100.0,
        },
        headers=headers,
    )
    assert cust_res.status_code == 201
    cust_id = cust_res.json()["id"]
    assert cust_res.json()["current_balance"] == 100.0

    # 4. Create Supplier with opening balance -$50 (we owe them)
    supp_res = client.post(
        "/parties",
        json={
            "name": f"Supplier A {uid}",
            "type": "supplier",
            "phone": "555-0202",
            "opening_balance": 50.0,  # $50 payable
        },
        headers=headers,
    )
    assert supp_res.status_code == 201
    supp_id = supp_res.json()["id"]

    # 5. Create Product with initial stock 50
    prod_res = client.post(
        "/products",
        json={
            "name": f"Widget {uid}",
            "sku": f"SKU-{uid}",
            "unit_price": 25.0,
            "cost_price": 15.0,
            "initial_stock": 50,
        },
        headers=headers,
    )
    assert prod_res.status_code == 201
    prod_id = prod_res.json()["id"]
    assert prod_res.json()["stock_quantity"] == 50

    # 6. DAILY TRANSACTIONS ENGINE
    # 6a. Sale to Customer on Credit: 10 units @ $25 = $250
    sale_res = client.post(
        "/transactions",
        json={
            "transaction_type": "sale",
            "party_id": cust_id,
            "amount": 250.0,
            "description": "Credit sale of 10 widgets",
            "payment_mode": "credit",
            "items": [
                {"product_id": prod_id, "description": "Widget", "quantity": 10, "unit_price": 25.0}
            ],
        },
        headers=headers,
    )
    assert sale_res.status_code == 201
    assert sale_res.json()["success"] is True

    # Check stock decreased from 50 to 40
    prod_check = client.get(f"/products/{prod_id}", headers=headers).json()
    assert prod_check["stock_quantity"] == 40

    # Check customer balance: $100 opening + $250 sale = $350
    cust_check = client.get(f"/parties/{cust_id}", headers=headers).json()
    assert cust_check["current_balance"] == 350.0

    # 6b. Receive Money from Customer: $200 received
    recv_res = client.post(
        "/transactions",
        json={
            "transaction_type": "receive_money",
            "party_id": cust_id,
            "amount": 200.0,
            "description": "Partial payment via Cash",
        },
        headers=headers,
    )
    assert recv_res.status_code == 201

    # Customer balance should now be $350 - $200 = $150
    cust_check2 = client.get(f"/parties/{cust_id}", headers=headers).json()
    assert cust_check2["current_balance"] == 150.0

    # 6c. Record Operating Expense: $50 Rent
    exp_res = client.post(
        "/transactions",
        json={
            "transaction_type": "expense",
            "amount": 50.0,
            "category": "Rent",
            "description": "Office rent payment",
        },
        headers=headers,
    )
    assert exp_res.status_code == 201

    # Cash in hand should be: +$200 (customer payment) - $50 (rent) = $150
    cash_sum = client.get("/cash-entries/summary", headers=headers).json()
    assert cash_sum["cash_in_hand"] == 150.0

    # 7. Check Reports
    # 7a. Profit & Loss: Sales $250, Expenses $50 -> Net Profit $200
    pl_res = client.get("/reports/profit-loss", headers=headers)
    assert pl_res.status_code == 200
    pl_data = pl_res.json()
    assert pl_data["total_sales"] == 250.0
    assert pl_data["total_expenses"] == 50.0
    assert pl_data["net_profit"] == 200.0

    # 7b. Balance Sheet
    bs_res = client.get("/reports/balance-sheet", headers=headers)
    assert bs_res.status_code == 200
    bs_data = bs_res.json()
    assert bs_data["cash_in_hand"] == 150.0
    assert bs_data["accounts_receivable"] == 150.0
    assert bs_data["total_assets"] > 0
    assert bs_data["total_liabilities"] >= 0

    # 7c. General Ledger report
    gl_res = client.get("/reports/transactions", headers=headers)
    assert gl_res.status_code == 200
    assert len(gl_res.json()) >= 4

    # 7d. General Ledger PDF export
    pdf_res = client.get("/reports/transactions/pdf", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 100

    # 8. Dashboard Overview
    dash_res = client.get("/dashboard/summary", headers=headers)
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    assert dash_data["cash_in_hand"] == 150.0
    assert dash_data["total_receivable"] == 150.0


def test_party_ledger_cash_sync():
    uid = uuid.uuid4().hex[:8]
    email = f"cash_test_{uid}@example.com"
    password = "Password123!"

    signup_res = client.post(
        "/auth/signup",
        json={"name": f"Tester {uid}", "email": email, "password": password},
    )
    token = signup_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    biz_res = client.post(
        "/businesses",
        json={"name": f"Shop {uid}", "business_type": "Retail"},
        headers=auth_headers,
    )
    biz_id = biz_res.json()["id"]
    headers = {**auth_headers, "X-Business-Id": biz_id}

    # 1. Create Customer
    cust_res = client.post(
        "/parties",
        json={"name": f"Customer {uid}", "type": "customer", "opening_balance": 50.0},
        headers=headers,
    )
    cust_id = cust_res.json()["id"]

    # Initial cash in hand should be 0
    cash_summary = client.get("/cash-entries/summary", headers=headers).json()
    assert cash_summary["cash_in_hand"] == 0.0

    # 2. Customer pays $30 (debit transaction via Party screen: "You Will Get")
    tx_res = client.post(
        f"/parties/{cust_id}/transactions",
        json={"type": "debit", "amount": 30.0, "description": "Cash payment received"},
        headers=headers,
    )
    assert tx_res.status_code == 201

    # Customer balance should now be 20.0
    cust_check = client.get(f"/parties/{cust_id}", headers=headers).json()
    assert cust_check["current_balance"] == 20.0

    # Cash in hand MUST now be $30.0!
    cash_after_cust = client.get("/cash-entries/summary", headers=headers).json()
    assert cash_after_cust["cash_in_hand"] == 30.0
    assert cash_after_cust["total_cash_in"] == 30.0

    # 3. Create Supplier and pay $10 (debit transaction via Party screen: "You Will Give")
    supp_res = client.post(
        "/parties",
        json={"name": f"Supplier {uid}", "type": "supplier", "opening_balance": 50.0},
        headers=headers,
    )
    supp_id = supp_res.json()["id"]

    tx_supp_res = client.post(
        f"/parties/{supp_id}/transactions",
        json={"type": "debit", "amount": 10.0, "description": "Cash paid to supplier"},
        headers=headers,
    )
    assert tx_supp_res.status_code == 201

    # Cash in hand should now be 30 - 10 = $20.0
    cash_final = client.get("/cash-entries/summary", headers=headers).json()
    assert cash_final["cash_in_hand"] == 20.0
    assert cash_final["total_cash_out"] == 10.0


def test_credit_sale_and_party_payment_auto_settles_invoice():
    uid = uuid.uuid4().hex[:8]
    email = f"settle_{uid}@example.com"
    password = "Password123!"

    signup_res = client.post(
        "/auth/signup",
        json={"name": f"Tester {uid}", "email": email, "password": password},
    )
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    biz_res = client.post(
        "/businesses",
        json={"name": f"Mart {uid}", "business_type": "Grocery"},
        headers=headers,
    )
    biz_id = biz_res.json()["id"]
    headers["X-Business-Id"] = biz_id

    # 1. Create customer
    cust_res = client.post(
        "/parties",
        json={"name": f"Ali {uid}", "type": "customer"},
        headers=headers,
    )
    cust_id = cust_res.json()["id"]

    # 2. Credit sale: $45 (Pay later)
    sale_res = client.post(
        "/transactions",
        json={
            "transaction_type": "sale",
            "party_id": cust_id,
            "amount": 45.0,
            "description": "Sale of 3 sacks of rice",
            "payment_mode": "credit",
        },
        headers=headers,
    )
    assert sale_res.status_code == 201

    # Check invoice status is unpaid
    invoices_res = client.get(f"/invoices?party_id={cust_id}", headers=headers).json()
    assert len(invoices_res) == 1
    inv = invoices_res[0]
    assert inv["status"] == "unpaid"
    assert inv["total_amount"] == 45.0
    assert inv["paid_amount"] == 0.0

    # 3. Customer pays $20 partial via Party screen ("You Will Get")
    part_pay = client.post(
        f"/parties/{cust_id}/transactions",
        json={"type": "debit", "amount": 20.0, "description": "Partial payment"},
        headers=headers,
    )
    assert part_pay.status_code == 201

    # Invoice should now automatically be "partial" with paid_amount=20.0
    inv_check1 = client.get(f"/invoices/{inv['id']}", headers=headers).json()
    assert inv_check1["status"] == "partial"
    assert inv_check1["paid_amount"] == 20.0

    # 4. Customer pays the remaining $25 via Party screen ("You Will Get")
    final_pay = client.post(
        f"/parties/{cust_id}/transactions",
        json={"type": "debit", "amount": 25.0, "description": "Final balance settlement"},
        headers=headers,
    )
    assert final_pay.status_code == 201

    # Invoice should now automatically be "paid" with paid_amount=45.0!
    inv_check2 = client.get(f"/invoices/{inv['id']}", headers=headers).json()
    assert inv_check2["status"] == "paid"
    assert inv_check2["paid_amount"] == 45.0

    # Customer balance should be 0.0
    party_check = client.get(f"/parties/{cust_id}", headers=headers).json()
    assert party_check["current_balance"] == 0.0



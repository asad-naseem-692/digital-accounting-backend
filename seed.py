"""
seed.py — Comprehensive realistic demo data seed script

Run via:
    uv run python seed.py

Creates a demo account and rich business records for immediate exploration:
- User: demo@example.com / Password123!
- Business: Apex Trading Co.
- Customers, Suppliers, Opening Balances
- Catalog Products with Inventory and Low Stock alerts
- Daily Sales Invoices, Purchase Bills, Cash Movements, Ledger statements
"""
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.party import Party
from app.models.ledger_transaction import LedgerTransaction
from app.models.product import Product
from app.models.stock_adjustment import StockAdjustment
from app.models.cash_entry import CashEntry
from app.models.invoice import Invoice


def seed():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # 1. Check or Create Demo User
        demo_email = "demo@example.com"
        user = db.scalar(select(User).where(User.email == demo_email))
        if not user:
            print("Creating Demo User: demo@example.com...")
            user = User(
                name="Demo Accountant",
                email=demo_email,
                password_hash=hash_password("Password123!"),
            )
            db.add(user)
            db.flush()
        else:
            print("Demo User already exists.")

        # 2. Check or Create Demo Business
        biz_name = "Apex Trading Co."
        membership = db.scalar(
            select(BusinessMember)
            .join(Business, BusinessMember.business_id == Business.id)
            .where(BusinessMember.user_id == user.id, Business.name == biz_name)
        )

        if membership:
            print(f"Demo Business '{biz_name}' already exists. Seeding complete.")
            return

        print(f"Creating Demo Business '{biz_name}'...")
        business = Business(
            name=biz_name,
            business_type="Wholesale & Distribution",
        )
        db.add(business)
        db.flush()

        member = BusinessMember(
            business_id=business.id,
            user_id=user.id,
            role="owner",
            can_edit=True,
            can_delete=True,
        )
        db.add(member)
        db.flush()

        # 3. Create Customers
        customers_data = [
            {"name": "Al-Rehman General Store", "phone": "+92 300 5551001", "opening_balance": 1450.0},
            {"name": "Bismillah Electronics", "phone": "+92 321 5551002", "opening_balance": 820.0},
            {"name": "Kamran Supermart", "phone": "+92 333 5551003", "opening_balance": 520.0},
            {"name": "Tariq Trading Hub", "phone": "+92 345 5551004", "opening_balance": 0.0},
        ]
        customers = []
        for c in customers_data:
            party = Party(
                business_id=business.id,
                name=c["name"],
                type="customer",
                phone=c["phone"],
                address="Commercial Market, Sector B",
            )
            db.add(party)
            db.flush()
            customers.append(party)

            if c["opening_balance"] > 0:
                db.add(
                    LedgerTransaction(
                        business_id=business.id,
                        party_id=party.id,
                        type="credit",
                        amount=c["opening_balance"],
                        description="Opening balance receivable",
                        date=now - timedelta(days=30),
                        created_by=user.id,
                    )
                )

        # 4. Create Suppliers
        suppliers_data = [
            {"name": "National Hardware Mills", "phone": "+92 42 35552001", "opening_balance": 2800.0},
            {"name": "Orient Packaging Ltd", "phone": "+92 21 35552002", "opening_balance": 950.0},
            {"name": "Global Tech Importers", "phone": "+92 51 35552003", "opening_balance": 1600.0},
        ]
        suppliers = []
        for s in suppliers_data:
            party = Party(
                business_id=business.id,
                name=s["name"],
                type="supplier",
                phone=s["phone"],
                address="Industrial Estate Zone 4",
            )
            db.add(party)
            db.flush()
            suppliers.append(party)

            if s["opening_balance"] > 0:
                db.add(
                    LedgerTransaction(
                        business_id=business.id,
                        party_id=party.id,
                        type="credit",
                        amount=s["opening_balance"],
                        description="Opening balance payable",
                        date=now - timedelta(days=30),
                        created_by=user.id,
                    )
                )

        # 5. Create Products
        products_data = [
            {"name": "Wireless Optical Mouse", "sku": "MOU-101", "unit_price": 18.50, "cost_price": 11.00, "stock": 45},
            {"name": "Mechanical RGB Keyboard", "sku": "KEY-202", "unit_price": 65.00, "cost_price": 42.00, "stock": 22},
            {"name": "USB-C Fast Cable (2m)", "sku": "CBL-303", "unit_price": 8.50, "cost_price": 3.80, "stock": 4}, # low stock
            {"name": "27-inch 4K IPS Monitor", "sku": "MON-404", "unit_price": 285.00, "cost_price": 210.00, "stock": 3}, # low stock
            {"name": "Noise Cancelling Headset", "sku": "AUD-505", "unit_price": 95.00, "cost_price": 62.00, "stock": 14},
            {"name": "Heavy Duty Extension Reel", "sku": "EXT-606", "unit_price": 32.00, "cost_price": 21.00, "stock": 28},
        ]
        products = []
        for p in products_data:
            prod = Product(
                business_id=business.id,
                name=p["name"],
                sku=p["sku"],
                unit_price=p["unit_price"],
                cost_price=p["cost_price"],
                stock_quantity=p["stock"],
            )
            db.add(prod)
            db.flush()
            products.append(prod)

            db.add(
                StockAdjustment(
                    business_id=business.id,
                    product_id=prod.id,
                    change_amount=p["stock"],
                    reason="Initial verified inventory batch",
                    created_at=now - timedelta(days=20),
                )
            )

        # 6. Create Daily Invoices & Bills
        # Sale 1 to Al-Rehman General Store (Paid)
        inv1 = Invoice(
            business_id=business.id,
            party_id=customers[0].id,
            invoice_type="sale",
            invoice_number="INV-20260901-0001",
            items=[
                {"product_id": products[0].id, "description": products[0].name, "quantity": 5, "unit_price": 18.50},
                {"product_id": products[1].id, "description": products[1].name, "quantity": 2, "unit_price": 65.00},
            ],
            total_amount=222.50,
            paid_amount=222.50,
            status="paid",
            date=now - timedelta(days=12),
        )
        db.add(inv1)

        # Sale 2 to Bismillah Electronics (Partial)
        inv2 = Invoice(
            business_id=business.id,
            party_id=customers[1].id,
            invoice_type="sale",
            invoice_number="INV-20260910-0002",
            items=[
                {"product_id": products[4].id, "description": products[4].name, "quantity": 4, "unit_price": 95.00},
            ],
            total_amount=380.00,
            paid_amount=200.00,
            status="partial",
            date=now - timedelta(days=5),
        )
        db.add(inv2)

        # Purchase Bill 1 from National Hardware Mills
        bill1 = Invoice(
            business_id=business.id,
            party_id=suppliers[0].id,
            invoice_type="purchase",
            invoice_number="BILL-20260905-0001",
            items=[
                {"product_id": products[0].id, "description": products[0].name, "quantity": 20, "unit_price": 11.00},
                {"product_id": products[1].id, "description": products[1].name, "quantity": 10, "unit_price": 42.00},
            ],
            total_amount=640.00,
            paid_amount=640.00,
            status="paid",
            date=now - timedelta(days=15),
        )
        db.add(bill1)

        # 7. Additional Customer Transactions & Payments
        # Customer 1 paid $500 cash
        db.add(
            LedgerTransaction(
                business_id=business.id,
                party_id=customers[0].id,
                type="debit",
                amount=500.0,
                description="Cash payment received against balance",
                date=now - timedelta(days=7),
                created_by=user.id,
            )
        )
        # Customer 2 delivered goods on credit
        db.add(
            LedgerTransaction(
                business_id=business.id,
                party_id=customers[1].id,
                type="credit",
                amount=380.0,
                description="Goods sold on credit (INV-20260910-0002)",
                date=now - timedelta(days=5),
                created_by=user.id,
            )
        )
        # Customer 2 made partial payment
        db.add(
            LedgerTransaction(
                business_id=business.id,
                party_id=customers[1].id,
                type="debit",
                amount=200.0,
                description="Cash receipt (INV-20260910-0002)",
                date=now - timedelta(days=4),
                created_by=user.id,
            )
        )

        # 8. Cash Book Entries
        cash_entries = [
            {"type": "cash_in", "amount": 5000.0, "category": "Capital Investment", "desc": "Initial cash opening injection", "days_ago": 25},
            {"type": "cash_in", "amount": 222.50, "category": "Sales", "desc": "Cash sale INV-20260901-0001", "days_ago": 12},
            {"type": "cash_in", "amount": 500.0, "category": "Customer Payment", "desc": "Receipt from Al-Rehman General Store", "days_ago": 7},
            {"type": "cash_in", "amount": 200.0, "category": "Customer Payment", "desc": "Receipt from Bismillah Electronics", "days_ago": 4},
            {"type": "cash_out", "amount": 1200.0, "category": "Rent", "desc": "Commercial warehouse monthly rent", "days_ago": 20},
            {"type": "cash_out", "amount": 640.0, "category": "Purchases", "desc": "Cash purchase payment (BILL-20260905-0001)", "days_ago": 15},
            {"type": "cash_out", "amount": 340.0, "category": "Utilities", "desc": "Commercial electricity bill", "days_ago": 10},
            {"type": "cash_out", "amount": 75.0, "category": "Tea & Refreshments", "desc": "Office pantry and guest refreshments", "days_ago": 2},
            {"type": "cash_out", "amount": 500.0, "category": "Supplier Payment", "desc": "Partial payment to National Hardware Mills", "days_ago": 1},
        ]

        for ce in cash_entries:
            db.add(
                CashEntry(
                    business_id=business.id,
                    type=ce["type"],
                    amount=ce["amount"],
                    category=ce["category"],
                    description=ce["desc"],
                    date=now - timedelta(days=ce["days_ago"]),
                    created_by=user.id,
                )
            )

        db.commit()
        print("Demo seed data successfully populated!")
        print("Credentials: demo@example.com / Password123!")
        print(f"Active Business: {biz_name}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

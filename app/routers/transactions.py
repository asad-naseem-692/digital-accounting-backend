from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.business import get_business_member, require_can_edit
from app.models.business_member import BusinessMember
from app.models.cash_entry import CashEntry
from app.models.invoice import Invoice
from app.models.ledger_transaction import LedgerTransaction
from app.models.party import Party
from app.models.product import Product
from app.models.stock_adjustment import StockAdjustment
from app.routers.invoices import allocate_payment_to_invoices
from app.schemas.invoice import InvoiceItemSchema

router = APIRouter()


class UnifiedTransactionCreate(BaseModel):
    transaction_type: str = Field(
        ...,
        pattern="^(sale|purchase|expense|receive_money|payment_money)$",
        description="Daily transaction category from the accounting workflow",
    )
    party_id: Optional[str] = None
    amount: float = Field(..., gt=0)
    category: Optional[str] = None
    description: str = Field(..., min_length=1)
    payment_mode: str = Field(default="cash", pattern="^(cash|credit)$")
    items: Optional[List[InvoiceItemSchema]] = None
    date: Optional[datetime] = None


class UnifiedTransactionResponse(BaseModel):
    success: bool
    transaction_type: str
    message: str
    amount: float
    party_id: Optional[str] = None
    created_records: List[str] = []


@router.post(
    "",
    response_model=UnifiedTransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Daily Transactions Engine — Automatic Accounting Records",
)
def record_daily_transaction(
    data: UnifiedTransactionCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    """
    Core Accounting Engine:
    Executes daily transactions with automatic double-entry journal postings
    to Customer Ledger, Supplier Ledger, Cash Book, and Stock Adjustments.
    """
    biz_id = member.business_id
    tx_date = data.date or datetime.now(timezone.utc)
    records_created = []

    # 1. SALES TRANSACTION
    if data.transaction_type == "sale":
        if not data.party_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer (party_id) is required for sales",
            )
        party = db.scalar(select(Party).where(Party.id == data.party_id, Party.business_id == biz_id))
        if not party:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

        # Create Invoice
        date_str = tx_date.strftime("%Y%m%d")
        inv_number = f"INV-{date_str}-{int(datetime.now(timezone.utc).timestamp()) % 10000:04d}"
        inv_items: List[dict[str, Any]] = []
        if data.items:
            for item in data.items:
                inv_items.append(item.model_dump())
                # Auto stock adjustment if product_id provided
                if item.product_id:
                    prod = db.scalar(select(Product).where(Product.id == item.product_id, Product.business_id == biz_id))
                    if prod:
                        prod.stock_quantity -= int(item.quantity)
                        db.add(
                            StockAdjustment(
                                business_id=biz_id,
                                product_id=prod.id,
                                change_amount=-int(item.quantity),
                                reason=f"Sale {inv_number}",
                            )
                        )
                        records_created.append(f"Stock adjusted for {prod.name} (-{item.quantity})")
        else:
            inv_items.append({"description": data.description, "quantity": 1, "unit_price": data.amount})

        is_cash = data.payment_mode == "cash"
        invoice = Invoice(
            business_id=biz_id,
            party_id=party.id,
            invoice_type="sale",
            invoice_number=inv_number,
            items=inv_items,
            total_amount=data.amount,
            paid_amount=data.amount if is_cash else 0.0,
            status="paid" if is_cash else "unpaid",
            date=tx_date,
        )
        db.add(invoice)
        records_created.append(f"Sales Invoice {inv_number} created")

        # Post to Customer Ledger
        # Credit transaction: record the sale amount owed
        tx_sale = LedgerTransaction(
            business_id=biz_id,
            party_id=party.id,
            type="credit",
            amount=data.amount,
            description=f"Sale: {data.description}",
            date=tx_date,
            created_by=member.user_id,
        )
        db.add(tx_sale)
        records_created.append("Customer ledger debited (receivable created)")

        # If paid via cash, also record the receipt
        if is_cash:
            tx_pay = LedgerTransaction(
                business_id=biz_id,
                party_id=party.id,
                type="debit",
                amount=data.amount,
                description=f"Cash payment for {inv_number}",
                date=tx_date,
                created_by=member.user_id,
            )
            db.add(tx_pay)
            cash_in = CashEntry(
                business_id=biz_id,
                type="cash_in",
                amount=data.amount,
                category="Sales",
                description=f"Cash sale from {party.name}",
                date=tx_date,
                created_by=member.user_id,
            )
            db.add(cash_in)
            records_created.append("Cash entry created (cash_in) & customer payment credited")

    # 2. PURCHASES TRANSACTION
    elif data.transaction_type == "purchase":
        if member.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Purchase transactions can only be recorded by the Business Owner.",
            )
        if not data.party_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Supplier (party_id) is required for purchases",
            )
        party = db.scalar(select(Party).where(Party.id == data.party_id, Party.business_id == biz_id))
        if not party:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

        date_str = tx_date.strftime("%Y%m%d")
        bill_number = f"BILL-{date_str}-{int(datetime.now(timezone.utc).timestamp()) % 10000:04d}"
        inv_items = []
        if data.items:
            for item in data.items:
                inv_items.append(item.model_dump())
                if item.product_id:
                    prod = db.scalar(select(Product).where(Product.id == item.product_id, Product.business_id == biz_id))
                    if prod:
                        prod.stock_quantity += int(item.quantity)
                        db.add(
                            StockAdjustment(
                                business_id=biz_id,
                                product_id=prod.id,
                                change_amount=int(item.quantity),
                                reason=f"Purchase {bill_number}",
                            )
                        )
                        records_created.append(f"Stock adjusted for {prod.name} (+{item.quantity})")
        else:
            inv_items.append({"description": data.description, "quantity": 1, "unit_price": data.amount})

        is_cash = data.payment_mode == "cash"
        invoice = Invoice(
            business_id=biz_id,
            party_id=party.id,
            invoice_type="purchase",
            invoice_number=bill_number,
            items=inv_items,
            total_amount=data.amount,
            paid_amount=data.amount if is_cash else 0.0,
            status="paid" if is_cash else "unpaid",
            date=tx_date,
        )
        db.add(invoice)
        records_created.append(f"Purchase Bill {bill_number} created")

        # Post to Supplier Ledger
        # Credit transaction = we owe supplier
        tx_bill = LedgerTransaction(
            business_id=biz_id,
            party_id=party.id,
            type="credit",
            amount=data.amount,
            description=f"Purchase: {data.description}",
            date=tx_date,
            created_by=member.user_id,
        )
        db.add(tx_bill)
        records_created.append("Supplier ledger credited (payable created)")

        if is_cash:
            tx_pay = LedgerTransaction(
                business_id=biz_id,
                party_id=party.id,
                type="debit",
                amount=data.amount,
                description=f"Cash payment for {bill_number}",
                date=tx_date,
                created_by=member.user_id,
            )
            db.add(tx_pay)
            cash_out = CashEntry(
                business_id=biz_id,
                type="cash_out",
                amount=data.amount,
                category="Purchases",
                description=f"Cash purchase from {party.name}",
                date=tx_date,
                created_by=member.user_id,
            )
            db.add(cash_out)
            records_created.append("Cash entry created (cash_out) & supplier payment debited")

    # 3. EXPENSES
    elif data.transaction_type == "expense":
        cat = data.category or "Operating Expense"
        cash_out = CashEntry(
            business_id=biz_id,
            type="cash_out",
            amount=data.amount,
            category=cat,
            description=data.description,
            date=tx_date,
            created_by=member.user_id,
        )
        db.add(cash_out)
        records_created.append(f"Cash expense recorded ({cat})")

    # 4. RECEIVE MONEY (Customer Payment)
    elif data.transaction_type == "receive_money":
        if not data.party_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer (party_id) is required to receive money",
            )
        party = db.scalar(select(Party).where(Party.id == data.party_id, Party.business_id == biz_id))
        if not party:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

        # Inflow in cash
        cash_in = CashEntry(
            business_id=biz_id,
            type="cash_in",
            amount=data.amount,
            category="Customer Payment",
            description=f"Payment received from {party.name} ({data.description})",
            date=tx_date,
            created_by=member.user_id,
        )
        db.add(cash_in)

        # Debit customer ledger (reduces their debt to us)
        tx_recv = LedgerTransaction(
            business_id=biz_id,
            party_id=party.id,
            type="debit",
            amount=data.amount,
            description=f"Payment received: {data.description}",
            date=tx_date,
            created_by=member.user_id,
        )
        db.add(tx_recv)
        settled_invs = allocate_payment_to_invoices(
            db, biz_id, party.id, data.amount, invoice_type="sale"
        )
        records_created.append(f"Cash in-hand increased by ${data.amount:,.2f}")
        records_created.append(f"Customer {party.name} ledger balance decreased")
        if settled_invs:
            records_created.append(f"Invoices updated: {', '.join(settled_invs)}")

    # 5. PAYMENT MONEY (Supplier Payment)
    elif data.transaction_type == "payment_money":
        if member.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Supplier payments are restricted to the Business Owner only.",
            )
        if not data.party_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Supplier (party_id) is required to make payment",
            )
        party = db.scalar(select(Party).where(Party.id == data.party_id, Party.business_id == biz_id))
        if not party:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

        # Outflow from cash
        cash_out = CashEntry(
            business_id=biz_id,
            type="cash_out",
            amount=data.amount,
            category="Supplier Payment",
            description=f"Payment made to {party.name} ({data.description})",
            date=tx_date,
            created_by=member.user_id,
        )
        db.add(cash_out)

        # Debit supplier ledger (reduces what we owe them)
        tx_pay = LedgerTransaction(
            business_id=biz_id,
            party_id=party.id,
            type="debit",
            amount=data.amount,
            description=f"Payment made: {data.description}",
            date=tx_date,
            created_by=member.user_id,
        )
        db.add(tx_pay)
        settled_bills = allocate_payment_to_invoices(
            db, biz_id, party.id, data.amount, invoice_type="purchase"
        )
        records_created.append(f"Cash in-hand decreased by ${data.amount:,.2f}")
        records_created.append(f"Payable to supplier {party.name} decreased")
        if settled_bills:
            records_created.append(f"Bills updated: {', '.join(settled_bills)}")

    db.commit()

    return UnifiedTransactionResponse(
        success=True,
        transaction_type=data.transaction_type,
        message=f"Successfully executed {data.transaction_type.replace('_', ' ').title()}",
        amount=data.amount,
        party_id=data.party_id,
        created_records=records_created,
    )

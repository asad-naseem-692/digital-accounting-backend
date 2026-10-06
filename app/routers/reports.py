import io
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, case
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.core.database import get_db
from app.dependencies.business import get_business_member
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.cash_entry import CashEntry
from app.models.invoice import Invoice
from app.models.ledger_transaction import LedgerTransaction
from app.models.party import Party
from app.models.product import Product

router = APIRouter()


class GeneralLedgerItem(BaseModel):
    id: str
    date: datetime
    source: str  # "ledger" | "cash" | "invoice"
    type: str
    category_or_party: str
    description: str
    debit: float = 0.0
    credit: float = 0.0
    amount: float
    created_by: str


class ProfitLossReport(BaseModel):
    total_sales: float
    total_purchases: float
    gross_profit: float
    total_expenses: float
    net_profit: float


class BalanceSheetReport(BaseModel):
    # Assets
    cash_in_hand: float
    accounts_receivable: float
    inventory_value: float
    total_assets: float
    # Liabilities
    accounts_payable: float
    total_liabilities: float
    # Equity
    net_worth: float


class DashboardOverview(BaseModel):
    cash_in_hand: float
    total_receivable: float
    total_payable: float
    total_invoices: int
    unpaid_invoices: int
    low_stock_products_count: int
    today_sales: float
    today_expenses: float


@router.get(
    "/dashboard/summary",
    response_model=DashboardOverview,
    status_code=status.HTTP_200_OK,
    summary="Dashboard Summary (FEAT-28)",
)
def get_dashboard_summary(
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Returns an executive financial health summary for the active business.
    """
    biz_id = member.business_id
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    # 1. Cash in hand
    cash_stmt = select(
        func.coalesce(func.sum(case((CashEntry.type == "cash_in", CashEntry.amount), else_=0.0)), 0.0)
        - func.coalesce(func.sum(case((CashEntry.type == "cash_out", CashEntry.amount), else_=0.0)), 0.0)
    ).where(CashEntry.business_id == biz_id)
    cash_in_hand = float(db.scalar(cash_stmt) or 0.0)

    # 2. Today's sales & expenses
    today_sales_stmt = select(func.coalesce(func.sum(Invoice.total_amount), 0.0)).where(
        Invoice.business_id == biz_id,
        Invoice.invoice_type == "sale",
        Invoice.date >= today_start,
    )
    today_sales = float(db.scalar(today_sales_stmt) or 0.0)

    today_exp_stmt = select(func.coalesce(func.sum(CashEntry.amount), 0.0)).where(
        CashEntry.business_id == biz_id,
        CashEntry.type == "cash_out",
        CashEntry.date >= today_start,
    )
    today_expenses = float(db.scalar(today_exp_stmt) or 0.0)

    # 3. Receivable / Payable
    parties_stmt = (
        select(
            Party.type,
            func.coalesce(
                func.sum(
                    case(
                        (LedgerTransaction.type == "credit", LedgerTransaction.amount),
                        else_=-LedgerTransaction.amount,
                    )
                ),
                0.0,
            ).label("balance"),
        )
        .join(LedgerTransaction, Party.id == LedgerTransaction.party_id)
        .where(Party.business_id == biz_id)
        .group_by(Party.id, Party.type)
    )
    rows = db.execute(parties_stmt).all()

    total_receivable = 0.0
    total_payable = 0.0
    for p_type, bal in rows:
        val = float(bal)
        if p_type == "customer" and val > 0:
            total_receivable += val
        elif p_type == "supplier" and val > 0:
            total_payable += val

    # 4. Invoices count
    total_inv_stmt = select(func.count(Invoice.id)).where(Invoice.business_id == biz_id)
    total_invoices = int(db.scalar(total_inv_stmt) or 0)

    unpaid_inv_stmt = select(func.count(Invoice.id)).where(
        Invoice.business_id == biz_id,
        Invoice.status != "paid",
    )
    unpaid_invoices = int(db.scalar(unpaid_inv_stmt) or 0)

    # 5. Low stock count
    low_stock_stmt = select(func.count(Product.id)).where(
        Product.business_id == biz_id,
        Product.stock_quantity <= 5,
    )
    low_stock_count = int(db.scalar(low_stock_stmt) or 0)

    return DashboardOverview(
        cash_in_hand=round(cash_in_hand, 2),
        total_receivable=round(total_receivable, 2),
        total_payable=round(total_payable, 2),
        total_invoices=total_invoices,
        unpaid_invoices=unpaid_invoices,
        low_stock_products_count=low_stock_count,
        today_sales=round(today_sales, 2),
        today_expenses=round(today_expenses, 2),
    )


@router.get(
    "/reports/profit-loss",
    response_model=ProfitLossReport,
    status_code=status.HTTP_200_OK,
    summary="Profit & Loss Statement",
)
def get_profit_loss(
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Computes Profit & Loss:
    Revenue (Sales) - Purchases = Gross Profit
    Gross Profit - Operating Expenses = Net Profit
    """
    biz_id = member.business_id

    # Total Sales
    sales_q = select(func.coalesce(func.sum(Invoice.total_amount), 0.0)).where(
        Invoice.business_id == biz_id,
        Invoice.invoice_type == "sale",
    )
    if from_date:
        sales_q = sales_q.where(Invoice.date >= from_date)
    if to_date:
        sales_q = sales_q.where(Invoice.date <= to_date)
    total_sales = float(db.scalar(sales_q) or 0.0)

    # Total Purchases
    purchases_q = select(func.coalesce(func.sum(Invoice.total_amount), 0.0)).where(
        Invoice.business_id == biz_id,
        Invoice.invoice_type == "purchase",
    )
    if from_date:
        purchases_q = purchases_q.where(Invoice.date >= from_date)
    if to_date:
        purchases_q = purchases_q.where(Invoice.date <= to_date)
    total_purchases = float(db.scalar(purchases_q) or 0.0)

    # Operating Expenses (Cash out excluding supplier bill payments)
    exp_q = select(func.coalesce(func.sum(CashEntry.amount), 0.0)).where(
        CashEntry.business_id == biz_id,
        CashEntry.type == "cash_out",
        CashEntry.category.notin_(["Supplier Payment", "Purchases"]),
    )
    if from_date:
        exp_q = exp_q.where(CashEntry.date >= from_date)
    if to_date:
        exp_q = exp_q.where(CashEntry.date <= to_date)
    total_expenses = float(db.scalar(exp_q) or 0.0)

    gross_profit = total_sales - total_purchases
    net_profit = gross_profit - total_expenses

    return ProfitLossReport(
        total_sales=round(total_sales, 2),
        total_purchases=round(total_purchases, 2),
        gross_profit=round(gross_profit, 2),
        total_expenses=round(total_expenses, 2),
        net_profit=round(net_profit, 2),
    )


@router.get(
    "/reports/balance-sheet",
    response_model=BalanceSheetReport,
    status_code=status.HTTP_200_OK,
    summary="Balance Sheet Statement",
)
def get_balance_sheet(
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Computes Balance Sheet:
    Assets: Cash in Hand + Accounts Receivable + Inventory Value
    Liabilities: Accounts Payable
    Net Worth = Total Assets - Total Liabilities
    """
    biz_id = member.business_id

    # 1. Cash in hand
    cash_stmt = select(
        func.coalesce(func.sum(case((CashEntry.type == "cash_in", CashEntry.amount), else_=0.0)), 0.0)
        - func.coalesce(func.sum(case((CashEntry.type == "cash_out", CashEntry.amount), else_=0.0)), 0.0)
    ).where(CashEntry.business_id == biz_id)
    cash_in_hand = max(0.0, float(db.scalar(cash_stmt) or 0.0))

    # 2. Receivables & Payables
    parties_stmt = (
        select(
            Party.type,
            func.coalesce(
                func.sum(
                    case(
                        (LedgerTransaction.type == "credit", LedgerTransaction.amount),
                        else_=-LedgerTransaction.amount,
                    )
                ),
                0.0,
            ).label("balance"),
        )
        .join(LedgerTransaction, Party.id == LedgerTransaction.party_id)
        .where(Party.business_id == biz_id)
        .group_by(Party.id, Party.type)
    )
    rows = db.execute(parties_stmt).all()

    accounts_receivable = 0.0
    accounts_payable = 0.0
    for p_type, bal in rows:
        val = float(bal)
        if p_type == "customer" and val > 0:
            accounts_receivable += val
        elif p_type == "supplier" and val > 0:
            accounts_payable += val

    # 3. Inventory valuation (qty * cost_price or unit_price)
    inv_stmt = select(
        func.coalesce(
            func.sum(
                Product.stock_quantity
                * case(
                    (Product.cost_price > 0, Product.cost_price),
                    else_=Product.unit_price,
                )
            ),
            0.0,
        )
    ).where(Product.business_id == biz_id, Product.stock_quantity > 0)
    inventory_val = float(db.scalar(inv_stmt) or 0.0)

    total_assets = cash_in_hand + accounts_receivable + inventory_val
    total_liabilities = accounts_payable
    net_worth = total_assets - total_liabilities

    return BalanceSheetReport(
        cash_in_hand=round(cash_in_hand, 2),
        accounts_receivable=round(accounts_receivable, 2),
        inventory_value=round(inventory_val, 2),
        total_assets=round(total_assets, 2),
        accounts_payable=round(accounts_payable, 2),
        total_liabilities=round(total_liabilities, 2),
        net_worth=round(net_worth, 2),
    )


@router.get(
    "/reports/transactions",
    response_model=List[GeneralLedgerItem],
    status_code=status.HTTP_200_OK,
    summary="General Ledger / Combined Transaction Report (FEAT-29)",
)
def get_transaction_report(
    type: Optional[str] = Query("all", pattern="^(all|ledger|cash)$"),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Returns a unified chronological general ledger combining party transactions and cash entries.
    """
    biz_id = member.business_id
    items: List[GeneralLedgerItem] = []

    # 1. Party Ledger Transactions
    if type in ["all", "ledger"]:
        tx_query = (
            select(LedgerTransaction, Party.name.label("party_name"))
            .join(Party, LedgerTransaction.party_id == Party.id)
            .where(LedgerTransaction.business_id == biz_id)
        )
        if from_date:
            tx_query = tx_query.where(LedgerTransaction.date >= from_date)
        if to_date:
            tx_query = tx_query.where(LedgerTransaction.date <= to_date)

        for tx, p_name in db.execute(tx_query).all():
            items.append(
                GeneralLedgerItem(
                    id=tx.id,
                    date=tx.date,
                    source="ledger",
                    type=tx.type,
                    category_or_party=p_name,
                    description=tx.description,
                    debit=float(tx.amount) if tx.type == "debit" else 0.0,
                    credit=float(tx.amount) if tx.type == "credit" else 0.0,
                    amount=float(tx.amount),
                    created_by=tx.created_by,
                )
            )

    # 2. Cash Entries
    if type in ["all", "cash"]:
        cash_query = select(CashEntry).where(CashEntry.business_id == biz_id)
        if from_date:
            cash_query = cash_query.where(CashEntry.date >= from_date)
        if to_date:
            cash_query = cash_query.where(CashEntry.date <= to_date)

        for ce in db.scalars(cash_query).all():
            items.append(
                GeneralLedgerItem(
                    id=ce.id,
                    date=ce.date,
                    source="cash",
                    type=ce.type,
                    category_or_party=ce.category,
                    description=ce.description or ce.category,
                    debit=float(ce.amount) if ce.type == "cash_out" else 0.0,
                    credit=float(ce.amount) if ce.type == "cash_in" else 0.0,
                    amount=float(ce.amount),
                    created_by=ce.created_by,
                )
            )

    # Sort descending (newest first)
    items.sort(key=lambda x: x.date, reverse=True)
    return items


@router.get(
    "/reports/transactions/pdf",
    summary="Report PDF Export (FEAT-30)",
)
def export_report_pdf(
    type: Optional[str] = Query("all", pattern="^(all|ledger|cash)$"),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Renders and exports a General Ledger transaction report PDF.
    """
    items = get_transaction_report(type, from_date, to_date, member, db)
    business = db.get(Business, member.business_id)

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Header
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 50, business.name if business else "Accounting Report")

    p.setFont("Helvetica-Bold", 13)
    p.drawRightString(width - 50, height - 50, "GENERAL LEDGER REPORT")

    p.setFont("Helvetica", 9)
    date_range_str = "All Time"
    if from_date and to_date:
        date_range_str = f"{from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}"
    p.drawString(50, height - 68, f"Period: {date_range_str} | Filter: {type.upper()}")
    p.drawRightString(width - 50, height - 68, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # Table Header
    p.line(50, height - 80, width - 50, height - 80)
    y = height - 95
    p.setFillColorRGB(0.95, 0.95, 0.95)
    p.rect(50, y - 4, width - 100, 16, fill=True, stroke=False)
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(55, y, "Date")
    p.drawString(120, y, "Source")
    p.drawString(170, y, "Account / Party")
    p.drawString(280, y, "Description")
    p.drawRightString(460, y, "Debit")
    p.drawRightString(width - 55, y, "Credit")

    y -= 18
    p.setFont("Helvetica", 8)
    total_debit = 0.0
    total_credit = 0.0

    for item in items[:150]:  # limit page overflow for first version
        if y < 60:
            p.showPage()
            y = height - 50
            p.setFont("Helvetica", 8)

        total_debit += item.debit
        total_credit += item.credit

        p.drawString(55, y, item.date.strftime("%Y-%m-%d"))
        p.drawString(120, y, item.source.upper())
        p.drawString(170, y, item.category_or_party[:20])
        p.drawString(280, y, item.description[:30])
        p.drawRightString(460, y, f"${item.debit:,.2f}" if item.debit > 0 else "-")
        p.drawRightString(width - 55, y, f"${item.credit:,.2f}" if item.credit > 0 else "-")
        y -= 14

    p.line(50, y - 2, width - 50, y - 2)
    y -= 14
    p.setFont("Helvetica-Bold", 9)
    p.drawString(280, y, "Total:")
    p.drawRightString(460, y, f"${total_debit:,.2f}")
    p.drawRightString(width - 55, y, f"${total_credit:,.2f}")

    p.showPage()
    p.save()

    buffer.seek(0)
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=general_ledger_report.pdf"},
    )

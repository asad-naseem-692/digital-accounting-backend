import io
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.core.database import get_db
from app.dependencies.business import get_business_member, require_can_edit
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.invoice import Invoice
from app.models.party import Party
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceRead,
    InvoiceStatusUpdate,
)

router = APIRouter()


def generate_invoice_number(db: Session, business_id: str, prefix: str = "INV") -> str:
    """Generate sequential number: INV-YYYYMMDD-XXXX."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"{prefix}-{date_str}-%"
    count_stmt = select(func.count(Invoice.id)).where(
        Invoice.business_id == business_id,
        Invoice.invoice_number.like(pattern),
    )
    count = (db.scalar(count_stmt) or 0) + 1
    return f"{prefix}-{date_str}-{count:04d}"


def allocate_payment_to_invoices(
    db: Session,
    business_id: str,
    party_id: str,
    payment_amount: float,
    invoice_type: str = "sale",
) -> List[str]:
    """
    Allocates received payment against unpaid / partial invoices in FIFO order.
    Updates paid_amount and status ('paid' or 'partial').
    Returns list of updated invoice numbers.
    """
    if payment_amount <= 0:
        return []

    unpaid_invoices = db.scalars(
        select(Invoice)
        .where(
            Invoice.business_id == business_id,
            Invoice.party_id == party_id,
            Invoice.invoice_type == invoice_type,
            Invoice.status.in_(["unpaid", "partial"]),
        )
        .order_by(Invoice.date.asc(), Invoice.created_at.asc())
    ).all()

    updated = []
    remaining = float(payment_amount)
    for inv in unpaid_invoices:
        if remaining <= 0:
            break

        total = float(inv.total_amount)
        paid = float(inv.paid_amount)
        outstanding = total - paid
        if outstanding <= 0:
            inv.status = "paid"
            continue

        if remaining >= outstanding:
            inv.paid_amount = total
            inv.status = "paid"
            remaining -= outstanding
            updated.append(inv.invoice_number)
        else:
            inv.paid_amount = round(paid + remaining, 2)
            inv.status = "partial"
            remaining = 0.0
            updated.append(inv.invoice_number)

    return updated


@router.post(
    "",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Invoice / Bill (FEAT-17)",
)
def create_invoice(
    data: InvoiceCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    """
    Creates a new sale invoice or purchase bill.
    Total amount is computed strictly server-side from line items.
    """
    party = db.scalar(
        select(Party).where(Party.id == data.party_id, Party.business_id == member.business_id)
    )
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found")

    inv_type = data.invoice_type or "sale"
    if inv_type == "purchase" and member.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Purchase bills can only be created by the Business Owner.",
        )
    prefix = "INV" if inv_type == "sale" else "BILL"
    inv_number = data.invoice_number or generate_invoice_number(db, member.business_id, prefix)

    # Compute total strictly server-side
    total = 0.0
    items_json = []
    for item in data.items:
        line_total = item.quantity * item.unit_price
        total += line_total
        items_json.append(item.model_dump())

    invoice = Invoice(
        business_id=member.business_id,
        party_id=data.party_id,
        invoice_type=inv_type,
        invoice_number=inv_number,
        items=items_json,
        total_amount=round(total, 2),
        paid_amount=0.0,
        status="unpaid",
        due_date=data.due_date,
        date=data.date or datetime.now(timezone.utc),
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    res = InvoiceRead.model_validate(invoice)
    res.party_name = party.name
    return res


@router.get(
    "",
    response_model=List[InvoiceRead],
    status_code=status.HTTP_200_OK,
    summary="View Invoices (FEAT-18)",
)
def view_invoices(
    party_id: Optional[str] = Query(None),
    invoice_type: Optional[str] = Query(None, pattern="^(sale|purchase)$"),
    status: Optional[str] = Query(None, pattern="^(unpaid|partial|paid)$"),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Lists invoices/bills for the active business with party name attached.
    Staff/cashiers can only view sales invoices.
    """
    query = (
        select(Invoice, Party.name.label("party_name"))
        .join(Party, Invoice.party_id == Party.id)
        .where(Invoice.business_id == member.business_id)
    )

    if member.role != "owner":
        # Staff accounts are restricted to customer sales invoices only
        query = query.where(Invoice.invoice_type == "sale")
    elif invoice_type:
        query = query.where(Invoice.invoice_type == invoice_type)
    if status:
        query = query.where(Invoice.status == status)
    if from_date:
        query = query.where(Invoice.date >= from_date)
    if to_date:
        query = query.where(Invoice.date <= to_date)

    query = query.order_by(Invoice.date.desc(), Invoice.created_at.desc())
    results = db.execute(query).all()

    items = []
    for inv, p_name in results:
        read_obj = InvoiceRead.model_validate(inv)
        read_obj.party_name = p_name
        items.append(read_obj)

    return items


@router.get(
    "/{invoice_id}",
    response_model=InvoiceRead,
    status_code=status.HTTP_200_OK,
    summary="Get Invoice Details",
)
def get_invoice(
    invoice_id: str,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """Get single invoice details with party name."""
    res = db.execute(
        select(Invoice, Party.name.label("party_name"))
        .join(Party, Invoice.party_id == Party.id)
        .where(Invoice.id == invoice_id, Invoice.business_id == member.business_id)
    ).first()

    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    inv, p_name = res
    if inv.invoice_type == "purchase" and member.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Purchase bills are restricted to the Business Owner.",
        )
    read_obj = InvoiceRead.model_validate(inv)
    read_obj.party_name = p_name
    return read_obj


@router.patch(
    "/{invoice_id}/status",
    response_model=InvoiceRead,
    status_code=status.HTTP_200_OK,
    summary="Update Invoice Status (FEAT-19)",
)
def update_invoice_status(
    invoice_id: str,
    data: InvoiceStatusUpdate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    """
    Updates the payment status of an invoice. Line items and amounts remain immutable.
    """
    invoice = db.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.business_id == member.business_id)
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice.invoice_type == "purchase" and member.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Purchase bills are restricted to the Business Owner.",
        )

    invoice.status = data.status
    if data.paid_amount is not None:
        invoice.paid_amount = data.paid_amount
    elif data.status == "paid":
        invoice.paid_amount = invoice.total_amount
    elif data.status == "unpaid":
        invoice.paid_amount = 0.0

    db.commit()
    db.refresh(invoice)

    party = db.get(Party, invoice.party_id)
    res = InvoiceRead.model_validate(invoice)
    res.party_name = party.name if party else None
    return res


def create_invoice_pdf_buffer(invoice: Invoice, party: Party, business: Business) -> io.BytesIO:
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Header
    p.setFont("Helvetica-Bold", 20)
    p.drawString(50, height - 50, business.name)

    p.setFont("Helvetica", 10)
    p.drawString(50, height - 68, f"Business Type: {business.business_type}")

    p.setFont("Helvetica-Bold", 14)
    title = "TAX INVOICE" if invoice.invoice_type == "sale" else "PURCHASE BILL"
    p.drawRightString(width - 50, height - 50, title)

    p.setFont("Helvetica", 10)
    p.drawRightString(width - 50, height - 68, f"No: {invoice.invoice_number}")
    p.drawRightString(width - 50, height - 82, f"Date: {invoice.date.strftime('%Y-%m-%d')}")
    p.drawRightString(width - 50, height - 96, f"Status: {invoice.status.upper()}")

    # Party Details
    p.line(50, height - 110, width - 50, height - 110)
    p.setFont("Helvetica-Bold", 11)
    party_label = "BILL TO:" if invoice.invoice_type == "sale" else "VENDOR:"
    p.drawString(50, height - 128, party_label)
    p.setFont("Helvetica", 11)
    p.drawString(120, height - 128, party.name)
    if party.phone:
        p.drawString(120, height - 144, f"Phone: {party.phone}")

    # Items Table Header
    y = height - 180
    p.setFillColorRGB(0.95, 0.95, 0.95)
    p.rect(50, y - 5, width - 100, 20, fill=True, stroke=False)
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y, "Description")
    p.drawRightString(350, y, "Qty")
    p.drawRightString(440, y, "Unit Price")
    p.drawRightString(width - 60, y, "Total")

    y -= 25
    p.setFont("Helvetica", 10)
    for item in (invoice.items or []):
        desc = str(item.get("description", ""))
        qty = float(item.get("quantity", 0))
        price = float(item.get("unit_price", 0))
        subtotal = qty * price

        p.drawString(60, y, desc[:45])
        p.drawRightString(350, y, f"{qty:g}")
        p.drawRightString(440, y, f"Rs {price:,.2f}")
        p.drawRightString(width - 60, y, f"Rs {subtotal:,.2f}")
        y -= 20

    # Total Amount
    p.line(50, y - 5, width - 50, y - 5)
    y -= 25
    p.setFont("Helvetica-Bold", 12)
    p.drawString(350, y, "Total Amount:")
    p.drawRightString(width - 60, y, f"Rs {invoice.total_amount:,.2f}")

    if invoice.paid_amount > 0:
        y -= 18
        p.setFont("Helvetica", 10)
        p.drawString(350, y, "Paid Amount:")
        p.drawRightString(width - 60, y, f"Rs {invoice.paid_amount:,.2f}")
        y -= 18
        p.setFont("Helvetica-Bold", 10)
        p.drawString(350, y, "Balance Due:")
        due = invoice.total_amount - invoice.paid_amount
        p.drawRightString(width - 60, y, f"Rs {due:,.2f}")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer


@router.get(
    "/public/{invoice_id}",
    summary="Public Invoice Details (for WhatsApp shared digital bill)",
)
def get_public_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
):
    """Public endpoint to view an invoice without authentication."""
    res = db.execute(
        select(Invoice, Party, Business)
        .join(Party, Invoice.party_id == Party.id)
        .join(Business, Invoice.business_id == Business.id)
        .where(Invoice.id == invoice_id)
    ).first()

    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    invoice, party, business = res
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "invoice_type": invoice.invoice_type,
        "date": invoice.date.isoformat(),
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "items": invoice.items or [],
        "total_amount": float(invoice.total_amount),
        "paid_amount": float(invoice.paid_amount),
        "status": invoice.status,
        "business_name": business.name,
        "business_type": business.business_type,
        "party_name": party.name,
        "party_phone": party.phone,
    }


@router.get(
    "/public/{invoice_id}/pdf",
    summary="Public Invoice PDF Download (for WhatsApp shared digital bill)",
)
def get_public_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
):
    """Public endpoint to download invoice PDF without authentication."""
    res = db.execute(
        select(Invoice, Party, Business)
        .join(Party, Invoice.party_id == Party.id)
        .join(Business, Invoice.business_id == Business.id)
        .where(Invoice.id == invoice_id)
    ).first()

    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    invoice, party, business = res
    buffer = create_invoice_pdf_buffer(invoice, party, business)
    filename = f"{invoice.invoice_number}.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/{invoice_id}/pdf",
    summary="Invoice PDF Export (FEAT-20)",
)
def export_invoice_pdf(
    invoice_id: str,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """Generates and returns an itemized PDF for the invoice using reportlab."""
    res = db.execute(
        select(Invoice, Party, Business)
        .join(Party, Invoice.party_id == Party.id)
        .join(Business, Invoice.business_id == Business.id)
        .where(Invoice.id == invoice_id, Invoice.business_id == member.business_id)
    ).first()

    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    invoice, party, business = res
    if invoice.invoice_type == "purchase" and member.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Purchase bills are restricted to the Business Owner.",
        )
    buffer = create_invoice_pdf_buffer(invoice, party, business)
    filename = f"{invoice.invoice_number}.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, case
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.business import get_business_member, require_can_edit
from app.models.business_member import BusinessMember
from app.models.cash_entry import CashEntry
from app.models.ledger_transaction import LedgerTransaction
from app.models.party import Party
from app.routers.invoices import allocate_payment_to_invoices
from app.schemas.party import (
    LedgerTransactionCreate,
    LedgerTransactionRead,
    PartiesSummary,
    PartyBalanceSummary,
    PartyCreate,
    PartyRead,
)

router = APIRouter()


def compute_party_balance(db: Session, party_id: str) -> float:
    """Calculate current balance = sum(credit) - sum(debit)."""
    stmt = select(
        func.coalesce(
            func.sum(
                case(
                    (LedgerTransaction.type == "credit", LedgerTransaction.amount),
                    else_=-LedgerTransaction.amount,
                )
            ),
            0.0,
        )
    ).where(LedgerTransaction.party_id == party_id)
    return float(db.scalar(stmt) or 0.0)


@router.post(
    "",
    response_model=PartyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Party (FEAT-09)",
)
def create_party(
    data: PartyCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    """
    Creates a new customer or supplier for the active business.
    If opening_balance is provided, an initial ledger entry is automatically booked.
    """
    party = Party(
        business_id=member.business_id,
        name=data.name.strip(),
        type=data.type,
        phone=data.phone.strip() if data.phone else None,
        address=data.address.strip() if data.address else None,
    )
    db.add(party)
    db.flush()

    initial_balance = 0.0
    if data.opening_balance and data.opening_balance != 0:
        tx_type = "credit" if data.opening_balance > 0 else "debit"
        tx = LedgerTransaction(
            business_id=member.business_id,
            party_id=party.id,
            type=tx_type,
            amount=abs(data.opening_balance),
            description="Opening balance",
            date=datetime.now(timezone.utc),
            created_by=member.user_id,
        )
        db.add(tx)
        initial_balance = float(data.opening_balance)

    db.commit()
    db.refresh(party)

    res = PartyRead.model_validate(party)
    res.current_balance = initial_balance
    return res


@router.get(
    "",
    response_model=List[PartyRead],
    status_code=status.HTTP_200_OK,
    summary="View Parties (FEAT-10)",
)
def view_parties(
    type: Optional[str] = Query(None, pattern="^(customer|supplier)$"),
    search: Optional[str] = Query(None),
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """List all parties for the business with their computed balance."""
    # Subquery for balances
    balance_sub = (
        select(
            LedgerTransaction.party_id,
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
        .where(LedgerTransaction.business_id == member.business_id)
        .group_by(LedgerTransaction.party_id)
        .subquery()
    )

    query = (
        select(Party, func.coalesce(balance_sub.c.balance, 0.0).label("balance"))
        .outerjoin(balance_sub, Party.id == balance_sub.c.party_id)
        .where(Party.business_id == member.business_id)
    )

    if type:
        query = query.where(Party.type == type)
    if search and search.strip():
        query = query.where(Party.name.ilike(f"%{search.strip()}%"))

    query = query.order_by(Party.name.asc())
    results = db.execute(query).all()

    items = []
    for party, bal in results:
        p_read = PartyRead.model_validate(party)
        p_read.current_balance = float(bal)
        items.append(p_read)

    return items


@router.get(
    "/summary",
    response_model=PartiesSummary,
    status_code=status.HTTP_200_OK,
    summary="Parties Overall Summary (FEAT-13)",
)
def get_parties_summary(
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Returns total receivable from customers and total payable to suppliers.
    """
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
        .where(Party.business_id == member.business_id)
        .group_by(Party.id, Party.type)
    )
    rows = db.execute(parties_stmt).all()

    total_receivable = 0.0
    total_payable = 0.0

    for p_type, bal in rows:
        val = float(bal)
        if p_type == "customer":
            if val > 0:
                total_receivable += val
        elif p_type == "supplier":
            # For suppliers: positive balance means we owe them (payable)
            if val > 0:
                total_payable += val
            elif val < 0:
                total_receivable += abs(val)

    return PartiesSummary(
        total_receivable=round(total_receivable, 2),
        total_payable=round(total_payable, 2),
    )


@router.get(
    "/{party_id}",
    response_model=PartyRead,
    status_code=status.HTTP_200_OK,
    summary="Get Party Details",
)
def get_party(
    party_id: str,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """Get single party with current balance."""
    party = db.scalar(
        select(Party).where(Party.id == party_id, Party.business_id == member.business_id)
    )
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found")

    res = PartyRead.model_validate(party)
    res.current_balance = compute_party_balance(db, party.id)
    return res


@router.post(
    "/{party_id}/transactions",
    response_model=LedgerTransactionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add Ledger Transaction (FEAT-11)",
)
def add_ledger_transaction(
    party_id: str,
    data: LedgerTransactionCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    """
    Record an immutable transaction ('credit' or 'debit') against a party.
    """
    party = db.scalar(
        select(Party).where(Party.id == party_id, Party.business_id == member.business_id)
    )
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found")

    tx = LedgerTransaction(
        business_id=member.business_id,
        party_id=party_id,
        type=data.type,
        amount=data.amount,
        description=data.description.strip(),
        date=data.date or datetime.now(timezone.utc),
        created_by=member.user_id,
    )
    db.add(tx)

    # Sync with Cash Book:
    # Customer debit = customer payment received -> Cash In
    # Supplier debit = payment made to supplier -> Cash Out
    if party.type == "customer" and data.type == "debit":
        cash_in = CashEntry(
            business_id=member.business_id,
            type="cash_in",
            amount=data.amount,
            category="Customer Payment",
            description=f"Received from {party.name} ({data.description.strip()})",
            date=tx.date,
            created_by=member.user_id,
        )
        db.add(cash_in)
        allocate_payment_to_invoices(
            db, member.business_id, party.id, data.amount, invoice_type="sale"
        )
    elif party.type == "supplier" and data.type == "debit":
        if member.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Supplier payments are restricted to the Business Owner only.",
            )
        cash_out = CashEntry(
            business_id=member.business_id,
            type="cash_out",
            amount=data.amount,
            category="Supplier Payment",
            description=f"Paid to {party.name} ({data.description.strip()})",
            date=tx.date,
            created_by=member.user_id,
        )
        db.add(cash_out)
        allocate_payment_to_invoices(
            db, member.business_id, party.id, data.amount, invoice_type="purchase"
        )

    db.commit()
    db.refresh(tx)

    return LedgerTransactionRead.model_validate(tx)


@router.get(
    "/{party_id}/transactions",
    response_model=List[LedgerTransactionRead],
    status_code=status.HTTP_200_OK,
    summary="View Party Ledger (FEAT-12)",
)
def view_party_ledger(
    party_id: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Returns ledger transactions for a party with calculated running balance.
    Sorted newest first.
    """
    party = db.scalar(
        select(Party).where(Party.id == party_id, Party.business_id == member.business_id)
    )
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found")

    # Fetch chronologically to compute running balance
    stmt = (
        select(LedgerTransaction)
        .where(
            LedgerTransaction.party_id == party_id,
            LedgerTransaction.business_id == member.business_id,
        )
        .order_by(LedgerTransaction.date.asc(), LedgerTransaction.created_at.asc())
    )
    all_txs = db.scalars(stmt).all()

    running = 0.0
    annotated = []
    for tx in all_txs:
        if tx.type == "credit":
            running += float(tx.amount)
        else:
            running -= float(tx.amount)

        read_tx = LedgerTransactionRead.model_validate(tx)
        read_tx.running_balance = round(running, 2)
        annotated.append(read_tx)

    # Apply date filters if provided
    if from_date:
        annotated = [t for t in annotated if t.date >= from_date]
    if to_date:
        annotated = [t for t in annotated if t.date <= to_date]

    # Return reverse chronological (newest first)
    annotated.reverse()
    return annotated


@router.get(
    "/{party_id}/balance",
    response_model=PartyBalanceSummary,
    status_code=status.HTTP_200_OK,
    summary="Party Balance Summary (FEAT-13)",
)
def get_party_balance(
    party_id: str,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """Returns computed current balance, total credit, and total debit for a single party."""
    party = db.scalar(
        select(Party).where(Party.id == party_id, Party.business_id == member.business_id)
    )
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found")

    credits_stmt = select(func.coalesce(func.sum(LedgerTransaction.amount), 0.0)).where(
        LedgerTransaction.party_id == party_id,
        LedgerTransaction.type == "credit",
    )
    debits_stmt = select(func.coalesce(func.sum(LedgerTransaction.amount), 0.0)).where(
        LedgerTransaction.party_id == party_id,
        LedgerTransaction.type == "debit",
    )

    total_credit = float(db.scalar(credits_stmt) or 0.0)
    total_debit = float(db.scalar(debits_stmt) or 0.0)
    current_balance = round(total_credit - total_debit, 2)

    return PartyBalanceSummary(
        party_id=party.id,
        party_name=party.name,
        current_balance=current_balance,
        total_credit=round(total_credit, 2),
        total_debit=round(total_debit, 2),
    )

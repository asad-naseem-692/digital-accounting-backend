from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select, case
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.business import get_business_member, require_can_edit
from app.models.business_member import BusinessMember
from app.models.cash_entry import CashEntry
from app.schemas.cash import CashEntryCreate, CashEntryRead, CashSummary

router = APIRouter()


@router.post(
    "",
    response_model=CashEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add Cash Entry (FEAT-14)",
)
def add_cash_entry(
    data: CashEntryCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    """
    Records an immutable cash movement (cash_in or cash_out).
    """
    entry = CashEntry(
        business_id=member.business_id,
        type=data.type,
        amount=data.amount,
        category=data.category.strip(),
        description=data.description.strip() if data.description else None,
        date=data.date or datetime.now(timezone.utc),
        created_by=member.user_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return CashEntryRead.model_validate(entry)


@router.get(
    "",
    response_model=List[CashEntryRead],
    status_code=status.HTTP_200_OK,
    summary="View Cash Book (FEAT-15)",
)
def view_cash_book(
    type: Optional[str] = Query(None, pattern="^(cash_in|cash_out)$"),
    category: Optional[str] = Query(None),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Returns cash book entries ordered newest first with computed running balance.
    """
    stmt = (
        select(CashEntry)
        .where(CashEntry.business_id == member.business_id)
        .order_by(CashEntry.date.asc(), CashEntry.created_at.asc())
    )
    all_entries = db.scalars(stmt).all()

    running = 0.0
    annotated = []
    for e in all_entries:
        if e.type == "cash_in":
            running += float(e.amount)
        else:
            running -= float(e.amount)

        read_item = CashEntryRead.model_validate(e)
        read_item.running_balance = round(running, 2)
        annotated.append(read_item)

    # Filter
    filtered = annotated
    if type:
        filtered = [x for x in filtered if x.type == type]
    if category and category.strip():
        filtered = [x for x in filtered if x.category.lower() == category.strip().lower()]
    if from_date:
        filtered = [x for x in filtered if x.date >= from_date]
    if to_date:
        filtered = [x for x in filtered if x.date <= to_date]

    filtered.reverse()
    return filtered


@router.get(
    "/summary",
    response_model=CashSummary,
    status_code=status.HTTP_200_OK,
    summary="Cash-in-Hand Summary (FEAT-16)",
)
def get_cash_summary(
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Returns cash-in-hand balance and totals for all-time and today.
    """
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    # All-time aggregates
    stmt = select(
        func.coalesce(
            func.sum(case((CashEntry.type == "cash_in", CashEntry.amount), else_=0.0)),
            0.0,
        ).label("total_in"),
        func.coalesce(
            func.sum(case((CashEntry.type == "cash_out", CashEntry.amount), else_=0.0)),
            0.0,
        ).label("total_out"),
    ).where(CashEntry.business_id == member.business_id)
    total_in, total_out = db.execute(stmt).one()

    # Today's aggregates
    today_stmt = select(
        func.coalesce(
            func.sum(case((CashEntry.type == "cash_in", CashEntry.amount), else_=0.0)),
            0.0,
        ).label("today_in"),
        func.coalesce(
            func.sum(case((CashEntry.type == "cash_out", CashEntry.amount), else_=0.0)),
            0.0,
        ).label("today_out"),
    ).where(CashEntry.business_id == member.business_id, CashEntry.date >= today_start)
    today_in, today_out = db.execute(today_stmt).one()

    total_in_f = float(total_in)
    total_out_f = float(total_out)
    cash_in_hand = round(total_in_f - total_out_f, 2)

    return CashSummary(
        cash_in_hand=cash_in_hand,
        total_cash_in=round(total_in_f, 2),
        total_cash_out=round(total_out_f, 2),
        today_cash_in=round(float(today_in), 2),
        today_cash_out=round(float(today_out), 2),
    )

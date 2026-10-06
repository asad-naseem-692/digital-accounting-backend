import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class CashEntry(Base):
    __tablename__ = "cash_entries"
    __table_args__ = (
        Index("ix_cash_entries_biz_date", "business_id", "date"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # "cash_in" | "cash_out"
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # Sales, Expense, Payment, etc.
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class SalaryPayment(Base):
    __tablename__ = "salary_payments"
    __table_args__ = (
        Index("ix_salary_business_month", "business_id", "month"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    worker_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "YYYY-MM" e.g. "2026-09"
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    days_present: Mapped[int] = mapped_column(nullable=False, default=0)
    days_half: Mapped[int] = mapped_column(nullable=False, default=0)
    working_days: Mapped[int] = mapped_column(nullable=False, default=26)
    gross_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    advance_deducted: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    net_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    cash_entry_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    worker: Mapped["Worker"] = relationship("Worker", back_populates="salary_payments")

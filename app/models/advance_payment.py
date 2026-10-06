import uuid
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import String, Numeric, Date, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AdvancePayment(Base):
    __tablename__ = "advance_payments"
    __table_args__ = (
        Index("ix_advance_business_worker", "business_id", "worker_id"),
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
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    is_deducted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cash_entry_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    worker: Mapped["Worker"] = relationship("Worker", back_populates="advance_payments")

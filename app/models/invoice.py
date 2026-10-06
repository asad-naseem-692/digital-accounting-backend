import uuid
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import String, Numeric, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_biz_type_date", "business_id", "invoice_type", "date"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    party_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="sale"
    )  # "sale" | "purchase"
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    paid_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unpaid"
    )  # "unpaid" | "partial" | "paid"
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    party: Mapped["Party"] = relationship("Party", back_populates="invoices")

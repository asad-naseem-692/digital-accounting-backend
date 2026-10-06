import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Party(Base):
    __tablename__ = "parties"
    __table_args__ = (
        Index("ix_parties_business_type", "business_id", "type"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # "customer" | "supplier"
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    transactions: Mapped[list["LedgerTransaction"]] = relationship(
        "LedgerTransaction", back_populates="party", cascade="all, delete-orphan", order_by="desc(LedgerTransaction.date)"
    )
    invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice", back_populates="party", cascade="all, delete-orphan"
    )

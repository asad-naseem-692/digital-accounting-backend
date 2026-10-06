import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"
    __table_args__ = (
        Index("ix_ledger_business_party_date", "business_id", "party_id", "date"),
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
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # "credit" | "debit"
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    party: Mapped["Party"] = relationship("Party", back_populates="transactions")

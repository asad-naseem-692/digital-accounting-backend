import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Numeric, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("business_id", "sku", name="uq_business_product_sku"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0.0)
    cost_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0.0)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    adjustments: Mapped[list["StockAdjustment"]] = relationship(
        "StockAdjustment", back_populates="product", cascade="all, delete-orphan", order_by="desc(StockAdjustment.created_at)"
    )

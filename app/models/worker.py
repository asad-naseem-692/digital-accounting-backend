import uuid
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import String, Numeric, Date, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Worker(Base):
    __tablename__ = "workers"
    __table_args__ = (
        Index("ix_workers_business_active", "business_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    designation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    monthly_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    joining_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    attendances: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="worker", cascade="all, delete-orphan")
    salary_payments: Mapped[list["SalaryPayment"]] = relationship("SalaryPayment", back_populates="worker", cascade="all, delete-orphan")
    advance_payments: Mapped[list["AdvancePayment"]] = relationship("AdvancePayment", back_populates="worker", cascade="all, delete-orphan")

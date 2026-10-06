import uuid
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import String, Date, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("worker_id", "date", name="uq_worker_date"),
        Index("ix_attendance_business_date", "business_id", "date"),
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
    date: Mapped[date] = mapped_column(Date, nullable=False)
    # "present" | "absent" | "half_day" | "leave"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="present")
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    worker: Mapped["Worker"] = relationship("Worker", back_populates="attendances")

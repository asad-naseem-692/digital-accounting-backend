"""
staff_book.py — Staff Book Router
Handles Workers, Attendance, Salary, and Advance Payments.
"""
import io
import calendar
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.business import get_business_member, require_can_edit
from app.models.advance_payment import AdvancePayment
from app.models.attendance import Attendance
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.cash_entry import CashEntry
from app.models.salary_payment import SalaryPayment
from app.models.worker import Worker

router = APIRouter()



# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class WorkerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    phone: Optional[str] = None
    designation: Optional[str] = None
    monthly_salary: float = Field(default=0.0, ge=0)
    joining_date: Optional[date] = None


class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    monthly_salary: Optional[float] = None
    joining_date: Optional[date] = None
    is_active: Optional[bool] = None


class WorkerRead(BaseModel):
    id: str
    business_id: str
    name: str
    phone: Optional[str]
    designation: Optional[str]
    monthly_salary: float
    joining_date: Optional[date]
    is_active: bool
    created_at: datetime
    today_status: Optional[str] = None  # today's attendance status

    model_config = {"from_attributes": True}


class AttendanceCreate(BaseModel):
    worker_id: str
    date: date
    status: str = Field(default="present", pattern="^(present|absent|half_day|leave)$")
    note: Optional[str] = None


class AttendanceBulkCreate(BaseModel):
    date: date
    records: List[AttendanceCreate]


class AttendanceRead(BaseModel):
    id: str
    worker_id: str
    date: date
    status: str
    note: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkerAttendanceMonth(BaseModel):
    worker_id: str
    worker_name: str
    monthly_salary: float
    days_present: int
    days_half: int
    days_absent: int
    days_leave: int
    working_days: int
    attendance: List[AttendanceRead]


class SalaryCalculation(BaseModel):
    worker_id: str
    worker_name: str
    month: str
    monthly_salary: float
    working_days: int
    days_present: int
    days_half: int
    payable_days: float
    gross_salary: float
    pending_advances: float
    net_salary: float


class SalaryPayCreate(BaseModel):
    worker_id: str
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    working_days: int = Field(default=26, ge=1, le=31)


class SalaryPaymentRead(BaseModel):
    id: str
    worker_id: str
    worker_name: Optional[str] = None
    month: str
    days_present: int
    days_half: int
    working_days: int
    gross_salary: float
    advance_deducted: float
    net_salary: float
    paid_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AdvanceCreate(BaseModel):
    worker_id: str
    amount: float = Field(..., gt=0)
    description: Optional[str] = None
    date: date


class AdvanceRead(BaseModel):
    id: str
    worker_id: str
    worker_name: Optional[str] = None
    amount: float
    description: Optional[str]
    date: date
    is_deducted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StaffBookSummary(BaseModel):
    total_workers: int
    present_today: int
    absent_today: int
    on_leave_today: int
    unmarked_today: int
    total_pending_advances: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_working_days(year: int, month: int) -> int:
    """Count working days in month (Mon-Sat, excluding Sundays)."""
    total = 0
    num_days = calendar.monthrange(year, month)[1]
    for d in range(1, num_days + 1):
        if date(year, month, d).weekday() != 6:  # 6 = Sunday
            total += 1
    return total


def get_month_attendance(db: Session, business_id: str, worker_id: str, year: int, month: int):
    """Get all attendance records for a worker in a given month."""
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    return db.scalars(
        select(Attendance)
        .where(
            Attendance.business_id == business_id,
            Attendance.worker_id == worker_id,
            Attendance.date >= first_day,
            Attendance.date <= last_day,
        )
        .order_by(Attendance.date)
    ).all()


def get_current_cash_in_hand(db: Session, business_id: str) -> float:
    cash_in = db.scalar(
        select(func.coalesce(func.sum(CashEntry.amount), 0.0)).where(
            CashEntry.business_id == business_id,
            CashEntry.type == "cash_in",
        )
    ) or 0.0
    cash_out = db.scalar(
        select(func.coalesce(func.sum(CashEntry.amount), 0.0)).where(
            CashEntry.business_id == business_id,
            CashEntry.type == "cash_out",
        )
    ) or 0.0
    return round(float(cash_in) - float(cash_out), 2)



# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

@router.post(
    "/workers",
    response_model=WorkerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add Worker",
)
def add_worker(
    data: WorkerCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    worker = Worker(
        business_id=member.business_id,
        name=data.name.strip(),
        phone=data.phone.strip() if data.phone else None,
        designation=data.designation.strip() if data.designation else None,
        monthly_salary=data.monthly_salary,
        joining_date=data.joining_date,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)

    res = WorkerRead.model_validate(worker)
    return res


@router.get(
    "/workers",
    response_model=List[WorkerRead],
    status_code=status.HTTP_200_OK,
    summary="List Workers",
)
def list_workers(
    active_only: bool = Query(default=True),
    for_date: Optional[date] = Query(default=None),
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    stmt = select(Worker).where(Worker.business_id == member.business_id)
    if active_only:
        stmt = stmt.where(Worker.is_active == True)
    stmt = stmt.order_by(Worker.name.asc())
    workers = db.scalars(stmt).all()

    target_date = for_date or date.today()
    # Fetch target day's attendance for all workers in one query
    worker_ids = [w.id for w in workers]
    today_records = {}
    if worker_ids:
        att_rows = db.scalars(
            select(Attendance).where(
                Attendance.business_id == member.business_id,
                Attendance.date == target_date,
                Attendance.worker_id.in_(worker_ids),
            )
        ).all()
        today_records = {a.worker_id: a.status for a in att_rows}

    result = []
    for w in workers:
        r = WorkerRead.model_validate(w)
        r.today_status = today_records.get(w.id)
        result.append(r)
    return result


@router.get(
    "/workers/{worker_id}",
    response_model=WorkerRead,
    status_code=status.HTTP_200_OK,
    summary="Get Worker Detail",
)
def get_worker(
    worker_id: str,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    worker = db.scalar(
        select(Worker).where(Worker.id == worker_id, Worker.business_id == member.business_id)
    )
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    res = WorkerRead.model_validate(worker)
    today = date.today()
    att = db.scalar(
        select(Attendance).where(
            Attendance.worker_id == worker_id,
            Attendance.date == today,
        )
    )
    res.today_status = att.status if att else None
    return res


@router.patch(
    "/workers/{worker_id}",
    response_model=WorkerRead,
    status_code=status.HTTP_200_OK,
    summary="Update Worker",
)
def update_worker(
    worker_id: str,
    data: WorkerUpdate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    worker = db.scalar(
        select(Worker).where(Worker.id == worker_id, Worker.business_id == member.business_id)
    )
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    if data.name is not None:
        worker.name = data.name.strip()
    if data.phone is not None:
        worker.phone = data.phone.strip() or None
    if data.designation is not None:
        worker.designation = data.designation.strip() or None
    if data.monthly_salary is not None:
        worker.monthly_salary = data.monthly_salary
    if data.joining_date is not None:
        worker.joining_date = data.joining_date
    if data.is_active is not None:
        worker.is_active = data.is_active

    db.commit()
    db.refresh(worker)
    return WorkerRead.model_validate(worker)


@router.delete(
    "/workers/{worker_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove Worker",
)
def remove_worker(
    worker_id: str,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    worker = db.scalar(
        select(Worker).where(Worker.id == worker_id, Worker.business_id == member.business_id)
    )
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")
    db.delete(worker)
    db.commit()


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

@router.post(
    "/attendance",
    response_model=AttendanceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Mark Attendance (single)",
)
def mark_attendance(
    data: AttendanceCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    worker = db.scalar(
        select(Worker).where(Worker.id == data.worker_id, Worker.business_id == member.business_id)
    )
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    existing = db.scalar(
        select(Attendance).where(
            Attendance.worker_id == data.worker_id,
            Attendance.date == data.date,
        )
    )
    if existing:
        existing.status = data.status
        existing.note = data.note
        db.commit()
        db.refresh(existing)
        return AttendanceRead.model_validate(existing)

    att = Attendance(
        business_id=member.business_id,
        worker_id=data.worker_id,
        date=data.date,
        status=data.status,
        note=data.note,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return AttendanceRead.model_validate(att)


@router.post(
    "/attendance/bulk",
    response_model=List[AttendanceRead],
    status_code=status.HTTP_201_CREATED,
    summary="Mark Attendance (bulk — all workers for one day)",
)
def mark_attendance_bulk(
    data: AttendanceBulkCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    results = []
    for rec in data.records:
        worker = db.scalar(
            select(Worker).where(Worker.id == rec.worker_id, Worker.business_id == member.business_id)
        )
        if not worker:
            continue

        existing = db.scalar(
            select(Attendance).where(
                Attendance.worker_id == rec.worker_id,
                Attendance.date == data.date,
            )
        )
        if existing:
            existing.status = rec.status
            existing.note = rec.note
            db.flush()
            results.append(existing)
        else:
            att = Attendance(
                business_id=member.business_id,
                worker_id=rec.worker_id,
                date=data.date,
                status=rec.status,
                note=rec.note,
            )
            db.add(att)
            db.flush()
            results.append(att)

    db.commit()
    return [AttendanceRead.model_validate(a) for a in results]


@router.get(
    "/attendance",
    response_model=List[WorkerAttendanceMonth],
    status_code=status.HTTP_200_OK,
    summary="Monthly Attendance — All Workers",
)
def get_monthly_attendance(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    year, mon = int(month[:4]), int(month[5:])
    workers = db.scalars(
        select(Worker).where(
            Worker.business_id == member.business_id,
            Worker.is_active == True,
        ).order_by(Worker.name)
    ).all()

    working_days = get_working_days(year, mon)
    result = []
    for w in workers:
        records = get_month_attendance(db, member.business_id, w.id, year, mon)
        days_present = sum(1 for r in records if r.status == "present")
        days_half = sum(1 for r in records if r.status == "half_day")
        days_absent = sum(1 for r in records if r.status == "absent")
        days_leave = sum(1 for r in records if r.status == "leave")
        result.append(WorkerAttendanceMonth(
            worker_id=w.id,
            worker_name=w.name,
            monthly_salary=float(w.monthly_salary),
            days_present=days_present,
            days_half=days_half,
            days_absent=days_absent,
            days_leave=days_leave,
            working_days=working_days,
            attendance=[AttendanceRead.model_validate(r) for r in records],
        ))
    return result


@router.get(
    "/attendance/{worker_id}",
    response_model=WorkerAttendanceMonth,
    status_code=status.HTTP_200_OK,
    summary="Monthly Attendance — Single Worker",
)
def get_worker_attendance(
    worker_id: str,
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    worker = db.scalar(
        select(Worker).where(Worker.id == worker_id, Worker.business_id == member.business_id)
    )
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    year, mon = int(month[:4]), int(month[5:])
    records = get_month_attendance(db, member.business_id, worker_id, year, mon)
    working_days = get_working_days(year, mon)

    return WorkerAttendanceMonth(
        worker_id=worker.id,
        worker_name=worker.name,
        monthly_salary=float(worker.monthly_salary),
        days_present=sum(1 for r in records if r.status == "present"),
        days_half=sum(1 for r in records if r.status == "half_day"),
        days_absent=sum(1 for r in records if r.status == "absent"),
        days_leave=sum(1 for r in records if r.status == "leave"),
        working_days=working_days,
        attendance=[AttendanceRead.model_validate(r) for r in records],
    )


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------

@router.get(
    "/salary/calculate",
    response_model=SalaryCalculation,
    status_code=status.HTTP_200_OK,
    summary="Calculate Payable Salary for a Worker",
)
def calculate_salary(
    worker_id: str = Query(...),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    working_days: int = Query(default=0, ge=0),
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    worker = db.scalar(
        select(Worker).where(Worker.id == worker_id, Worker.business_id == member.business_id)
    )
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    year, mon = int(month[:4]), int(month[5:])
    wd = working_days if working_days > 0 else get_working_days(year, mon)
    records = get_month_attendance(db, member.business_id, worker_id, year, mon)

    days_present = sum(1 for r in records if r.status == "present")
    days_half = sum(1 for r in records if r.status == "half_day")
    payable_days = days_present + (days_half * 0.5)

    monthly_sal = float(worker.monthly_salary)
    gross = round((payable_days / wd) * monthly_sal, 2) if wd > 0 else 0.0

    # Pending advances (not yet deducted)
    pending_adv = db.scalar(
        select(func.coalesce(func.sum(AdvancePayment.amount), 0.0)).where(
            AdvancePayment.business_id == member.business_id,
            AdvancePayment.worker_id == worker_id,
            AdvancePayment.is_deducted == False,
        )
    ) or 0.0
    pending_adv = float(pending_adv)

    net = round(max(gross - pending_adv, 0.0), 2)

    return SalaryCalculation(
        worker_id=worker.id,
        worker_name=worker.name,
        month=month,
        monthly_salary=monthly_sal,
        working_days=wd,
        days_present=days_present,
        days_half=days_half,
        payable_days=payable_days,
        gross_salary=gross,
        pending_advances=pending_adv,
        net_salary=net,
    )


@router.post(
    "/salary/pay",
    response_model=SalaryPaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Pay Salary — creates CashEntry automatically",
)
def pay_salary(
    data: SalaryPayCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    worker = db.scalar(
        select(Worker).where(Worker.id == data.worker_id, Worker.business_id == member.business_id)
    )
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    year, mon = int(data.month[:4]), int(data.month[5:])
    wd = data.working_days if data.working_days > 0 else get_working_days(year, mon)
    records = get_month_attendance(db, member.business_id, data.worker_id, year, mon)

    days_present = sum(1 for r in records if r.status == "present")
    days_half = sum(1 for r in records if r.status == "half_day")
    payable_days = days_present + (days_half * 0.5)

    monthly_sal = float(worker.monthly_salary)
    gross = round((payable_days / wd) * monthly_sal, 2) if wd > 0 else 0.0

    # Get pending advances
    pending_advances = db.scalars(
        select(AdvancePayment).where(
            AdvancePayment.business_id == member.business_id,
            AdvancePayment.worker_id == data.worker_id,
            AdvancePayment.is_deducted == False,
        )
    ).all()
    advance_total = sum(float(a.amount) for a in pending_advances)
    net = round(max(gross - advance_total, 0.0), 2)
    amount_to_pay = net if net > 0 else gross

    # Validate that sufficient cash in hand is available
    if amount_to_pay > 0:
        available_cash = get_current_cash_in_hand(db, member.business_id)
        if amount_to_pay > available_cash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient Cash in Hand! Available: Rs {available_cash:,.2f}, Required: Rs {amount_to_pay:,.2f}. Please add cash in Cash Book first before paying salary."
            )

    # Create Cash Out entry in Cash Book
    now = datetime.now(timezone.utc)
    month_label = date(year, mon, 1).strftime("%B %Y")
    cash_out = CashEntry(
        business_id=member.business_id,
        type="cash_out",
        amount=amount_to_pay,
        category="Salary",
        description=f"Salary paid to {worker.name} — {month_label}",
        date=now,
        created_by=member.user_id,
    )
    db.add(cash_out)
    db.flush()

    # Create Salary Payment record
    sp = SalaryPayment(
        business_id=member.business_id,
        worker_id=data.worker_id,
        month=data.month,
        days_present=days_present,
        days_half=days_half,
        working_days=wd,
        gross_salary=gross,
        advance_deducted=round(advance_total, 2),
        net_salary=net,
        cash_entry_id=cash_out.id,
        paid_at=now,
    )
    db.add(sp)

    # Mark advances as deducted
    for adv in pending_advances:
        adv.is_deducted = True

    db.commit()
    db.refresh(sp)

    res = SalaryPaymentRead.model_validate(sp)
    res.worker_name = worker.name
    return res


@router.get(
    "/salary/history",
    response_model=List[SalaryPaymentRead],
    status_code=status.HTTP_200_OK,
    summary="Salary Payment History",
)
def salary_history(
    worker_id: Optional[str] = Query(default=None),
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    stmt = select(SalaryPayment, Worker.name.label("wname")).join(
        Worker, SalaryPayment.worker_id == Worker.id
    ).where(SalaryPayment.business_id == member.business_id)
    if worker_id:
        stmt = stmt.where(SalaryPayment.worker_id == worker_id)
    stmt = stmt.order_by(SalaryPayment.paid_at.desc())

    rows = db.execute(stmt).all()
    result = []
    for sp, wname in rows:
        r = SalaryPaymentRead.model_validate(sp)
        r.worker_name = wname
        result.append(r)
    return result


def generate_salary_slip_pdf(
    payment: SalaryPayment,
    worker: Worker,
    business: Business,
) -> io.BytesIO:
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Header
    p.setFont("Helvetica-Bold", 20)
    p.drawString(50, height - 50, business.name)

    p.setFont("Helvetica", 10)
    p.drawString(50, height - 68, f"Business Category: {business.business_type or 'General Store'}")

    p.setFont("Helvetica-Bold", 14)
    p.drawRightString(width - 50, height - 50, "SALARY PAYSLIP")

    p.setFont("Helvetica-Bold", 11)
    p.drawRightString(width - 50, height - 68, f"Month: {payment.month}")
    p.setFont("Helvetica", 9)
    p.drawRightString(width - 50, height - 82, f"Slip ID: {payment.id[:8].upper()}")
    p.drawRightString(width - 50, height - 94, f"Date: {payment.paid_at.strftime('%Y-%m-%d')}")

    # Divider
    p.setLineWidth(1)
    p.line(50, height - 105, width - 50, height - 105)

    # Worker Info Box
    p.setFillColorRGB(0.96, 0.97, 0.99)
    p.rect(50, height - 170, width - 100, 58, fill=True, stroke=False)
    p.setFillColorRGB(0, 0, 0)

    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, height - 123, "EMPLOYEE INFORMATION")

    p.setFont("Helvetica", 9)
    p.drawString(60, height - 140, f"Worker Name: {worker.name}")
    p.drawString(60, height - 155, f"Designation: {worker.designation or 'Staff / Worker'}")

    p.drawString(320, height - 140, f"Contact: {worker.phone or 'N/A'}")
    if worker.joining_date:
        p.drawString(320, height - 155, f"Joined: {worker.joining_date.strftime('%Y-%m-%d')}")
    else:
        p.drawString(320, height - 155, "Joined: N/A")

    # Attendance Summary Box
    p.setFillColorRGB(0.96, 0.97, 0.99)
    p.rect(50, height - 235, width - 100, 55, fill=True, stroke=False)
    p.setFillColorRGB(0, 0, 0)

    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, height - 188, "ATTENDANCE BREAKDOWN")

    p.setFont("Helvetica", 9)
    p.drawString(60, height - 205, f"Working Days: {payment.working_days}")
    p.drawString(180, height - 205, f"Present Days: {payment.days_present}")
    p.drawString(300, height - 205, f"Half Days: {payment.days_half}")
    payable_days = payment.days_present + (payment.days_half * 0.5)
    p.drawString(420, height - 205, f"Payable Days: {payable_days:g}")

    # Salary Computations Table
    y = height - 260
    p.setFillColorRGB(0.92, 0.93, 0.95)
    p.rect(50, y - 5, width - 100, 20, fill=True, stroke=False)
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y, "Salary Component / Description")
    p.drawRightString(350, y, "Type")
    p.drawRightString(width - 60, y, "Amount (PKR)")

    y -= 25
    p.setFont("Helvetica", 9)

    # Base Monthly Salary
    p.drawString(60, y, "Monthly Base Rate (Full Month)")
    p.drawRightString(350, y, "Base")
    p.drawRightString(width - 60, y, f"Rs {float(worker.monthly_salary):,.2f}")
    y -= 20

    # Earned / Gross Salary
    p.drawString(60, y, f"Gross Earned Salary ({payable_days:g} days / {payment.working_days} working days)")
    p.drawRightString(350, y, "Earning")
    p.drawRightString(width - 60, y, f"Rs {float(payment.gross_salary):,.2f}")
    y -= 20

    # Advance Deductions
    p.drawString(60, y, "Advance Salary Deductions")
    p.drawRightString(350, y, "Deduction")
    adv_ded = float(payment.advance_deducted or 0)
    p.drawRightString(width - 60, y, f"- Rs {adv_ded:,.2f}" if adv_ded > 0 else "Rs 0.00")
    y -= 20

    # Total Line
    p.setLineWidth(1)
    p.line(50, y + 5, width - 50, y + 5)
    y -= 15

    # Net Salary Highlight Box
    p.setFillColorRGB(0.93, 0.96, 0.93)
    p.rect(50, y - 10, width - 100, 30, fill=True, stroke=False)
    p.setFillColorRGB(0.08, 0.45, 0.2)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(60, y, "NET SALARY PAID:")
    p.drawRightString(width - 60, y, f"Rs {float(payment.net_salary):,.2f}")

    p.setFillColorRGB(0, 0, 0)

    # Payment Status & Mode
    y -= 40
    p.setFont("Helvetica", 9)
    p.drawString(60, y, "Payment Mode: Cash in Hand (Cash Book Synchronized)")
    p.drawRightString(width - 60, y, "Status: COMPLETED / PAID")

    # Signatures
    y -= 90
    p.setLineWidth(0.8)
    p.line(70, y, 220, y)
    p.line(width - 220, y, width - 70, y)

    p.setFont("Helvetica", 9)
    p.drawCentredString(145, y - 15, "Employee / Worker Signature")
    p.drawCentredString(width - 145, y - 15, "Authorized Signatory / Stamp")

    # Footer
    p.setFont("Helvetica-Oblique", 8)
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawCentredString(width / 2, 40, "This is an official computer-generated salary slip generated via Digital Khata & Bookkeeping System.")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer


@router.get(
    "/salary/{payment_id}/pdf",
    summary="Export Salary Slip PDF",
)
def export_salary_slip_pdf(
    payment_id: str,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """Generates and returns an itemized Salary Slip PDF."""
    res = db.execute(
        select(SalaryPayment, Worker, Business)
        .join(Worker, SalaryPayment.worker_id == Worker.id)
        .join(Business, SalaryPayment.business_id == Business.id)
        .where(
            SalaryPayment.id == payment_id,
            SalaryPayment.business_id == member.business_id,
        )
    ).first()

    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Salary payment not found")

    payment, worker, business = res
    buffer = generate_salary_slip_pdf(payment, worker, business)
    filename = f"Salary_Slip_{worker.name.replace(' ', '_')}_{payment.month}.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/salary/public/{payment_id}/pdf",
    summary="Public Salary Slip PDF Download",
)
def export_public_salary_slip_pdf(
    payment_id: str,
    db: Session = Depends(get_db),
):
    """Public endpoint to download salary slip PDF without authentication."""
    res = db.execute(
        select(SalaryPayment, Worker, Business)
        .join(Worker, SalaryPayment.worker_id == Worker.id)
        .join(Business, SalaryPayment.business_id == Business.id)
        .where(SalaryPayment.id == payment_id)
    ).first()

    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Salary payment not found")

    payment, worker, business = res
    buffer = generate_salary_slip_pdf(payment, worker, business)
    filename = f"Salary_Slip_{worker.name.replace(' ', '_')}_{payment.month}.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post(
    "/advances",
    response_model=AdvanceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record Advance Payment",
)
def record_advance(
    data: AdvanceCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    worker = db.scalar(
        select(Worker).where(Worker.id == data.worker_id, Worker.business_id == member.business_id)
    )
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    available_cash = get_current_cash_in_hand(db, member.business_id)
    if data.amount > available_cash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient Cash in Hand! Available: Rs {available_cash:,.2f}, Required: Rs {data.amount:,.2f}. Please add cash in Cash Book first before giving advance."
        )

    # Create cash out entry
    cash_out = CashEntry(
        business_id=member.business_id,
        type="cash_out",
        amount=data.amount,
        category="Advance Salary",
        description=f"Advance to {worker.name}" + (f" — {data.description}" if data.description else ""),
        date=datetime.combine(data.date, datetime.min.time()).replace(tzinfo=timezone.utc),
        created_by=member.user_id,
    )
    db.add(cash_out)
    db.flush()

    adv = AdvancePayment(
        business_id=member.business_id,
        worker_id=data.worker_id,
        amount=data.amount,
        description=data.description,
        date=data.date,
        is_deducted=False,
        cash_entry_id=cash_out.id,
    )
    db.add(adv)
    db.commit()
    db.refresh(adv)

    res = AdvanceRead.model_validate(adv)
    res.worker_name = worker.name
    return res


@router.get(
    "/advances",
    response_model=List[AdvanceRead],
    status_code=status.HTTP_200_OK,
    summary="List Advance Payments",
)
def list_advances(
    worker_id: Optional[str] = Query(default=None),
    pending_only: bool = Query(default=False),
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    stmt = select(AdvancePayment, Worker.name.label("wname")).join(
        Worker, AdvancePayment.worker_id == Worker.id
    ).where(AdvancePayment.business_id == member.business_id)
    if worker_id:
        stmt = stmt.where(AdvancePayment.worker_id == worker_id)
    if pending_only:
        stmt = stmt.where(AdvancePayment.is_deducted == False)
    stmt = stmt.order_by(AdvancePayment.date.desc())

    rows = db.execute(stmt).all()
    result = []
    for adv, wname in rows:
        r = AdvanceRead.model_validate(adv)
        r.worker_name = wname
        result.append(r)
    return result


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

@router.get(
    "/summary",
    response_model=StaffBookSummary,
    status_code=status.HTTP_200_OK,
    summary="Staff Book Dashboard Summary",
)
def get_staff_summary(
    for_date: Optional[date] = Query(default=None),
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    target_date = for_date or date.today()
    biz_id = member.business_id

    total_workers = db.scalar(
        select(func.count(Worker.id)).where(
            Worker.business_id == biz_id, Worker.is_active == True
        )
    ) or 0

    # Today's attendance
    today_records = db.scalars(
        select(Attendance).where(
            Attendance.business_id == biz_id,
            Attendance.date == target_date,
        )
    ).all()

    present_today = sum(1 for a in today_records if a.status in ("present", "half_day"))
    absent_today = sum(1 for a in today_records if a.status == "absent")
    on_leave_today = sum(1 for a in today_records if a.status == "leave")
    marked_today = len(today_records)
    unmarked_today = max(total_workers - marked_today, 0)

    # Pending advances total
    pending_adv = db.scalar(
        select(func.coalesce(func.sum(AdvancePayment.amount), 0.0)).where(
            AdvancePayment.business_id == biz_id,
            AdvancePayment.is_deducted == False,
        )
    ) or 0.0

    return StaffBookSummary(
        total_workers=total_workers,
        present_today=present_today,
        absent_today=absent_today,
        on_leave_today=on_leave_today,
        unmarked_today=unmarked_today,
        total_pending_advances=round(float(pending_adv), 2),
    )

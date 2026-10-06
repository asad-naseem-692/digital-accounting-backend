from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CashEntryCreate(BaseModel):
    type: str = Field(..., pattern="^(cash_in|cash_out)$")
    amount: float = Field(..., gt=0)
    category: str = Field(..., min_length=1)
    description: Optional[str] = None
    date: Optional[datetime] = None


class CashEntryRead(BaseModel):
    id: str
    business_id: str
    type: str
    amount: float
    category: str
    description: Optional[str] = None
    date: datetime
    created_by: str
    created_at: datetime
    running_balance: Optional[float] = None

    model_config = {"from_attributes": True}


class CashSummary(BaseModel):
    cash_in_hand: float
    total_cash_in: float
    total_cash_out: float
    today_cash_in: float
    today_cash_out: float

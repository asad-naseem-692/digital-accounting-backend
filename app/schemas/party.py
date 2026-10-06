from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class PartyCreate(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., pattern="^(customer|supplier)$")
    phone: Optional[str] = None
    address: Optional[str] = None
    opening_balance: Optional[float] = Field(default=0.0)


class PartyRead(BaseModel):
    id: str
    business_id: str
    name: str
    type: str
    phone: Optional[str] = None
    address: Optional[str] = None
    current_balance: float = 0.0
    created_at: datetime

    model_config = {"from_attributes": True}


class LedgerTransactionCreate(BaseModel):
    type: str = Field(..., pattern="^(credit|debit)$")
    amount: float = Field(..., gt=0)
    description: str = Field(..., min_length=1)
    date: Optional[datetime] = None


class LedgerTransactionRead(BaseModel):
    id: str
    business_id: str
    party_id: str
    type: str
    amount: float
    description: str
    date: datetime
    created_by: str
    created_at: datetime
    running_balance: Optional[float] = None

    model_config = {"from_attributes": True}


class PartyBalanceSummary(BaseModel):
    party_id: str
    party_name: str
    current_balance: float
    total_credit: float
    total_debit: float


class PartiesSummary(BaseModel):
    total_receivable: float
    total_payable: float

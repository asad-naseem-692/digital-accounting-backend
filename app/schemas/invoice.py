from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class InvoiceItemSchema(BaseModel):
    product_id: Optional[str] = None
    description: str = Field(..., min_length=1)
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)


class InvoiceCreate(BaseModel):
    party_id: str
    invoice_type: Optional[str] = Field(default="sale", pattern="^(sale|purchase)$")
    invoice_number: Optional[str] = None
    items: List[InvoiceItemSchema] = Field(..., min_length=1)
    due_date: Optional[datetime] = None
    date: Optional[datetime] = None


class InvoiceStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(unpaid|partial|paid)$")
    paid_amount: Optional[float] = Field(default=None, ge=0)


class InvoiceRead(BaseModel):
    id: str
    business_id: str
    party_id: str
    party_name: Optional[str] = None
    invoice_type: str
    invoice_number: str
    items: List[InvoiceItemSchema]
    total_amount: float
    paid_amount: float
    status: str
    due_date: Optional[datetime] = None
    date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}

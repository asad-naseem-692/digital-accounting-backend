from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1)
    sku: Optional[str] = None
    unit_price: float = Field(..., ge=0)
    cost_price: Optional[float] = Field(default=0.0, ge=0)
    initial_stock: Optional[int] = Field(default=0, ge=0)


class ProductRead(BaseModel):
    id: str
    business_id: str
    name: str
    sku: Optional[str] = None
    unit_price: float
    cost_price: float
    stock_quantity: int
    created_at: datetime

    model_config = {"from_attributes": True}


class StockAdjustmentCreate(BaseModel):
    change_amount: int = Field(..., description="Positive for in/restock, negative for out/sold/damaged")
    reason: str = Field(..., min_length=1)


class StockAdjustmentRead(BaseModel):
    id: str
    business_id: str
    product_id: str
    change_amount: int
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}

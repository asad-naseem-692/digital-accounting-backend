from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class BusinessCreate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    business_type: str = Field(default="General", min_length=1)

    @model_validator(mode="after")
    def validate_name(self):
        val = self.name or self.business_name
        if not val or not val.strip():
            raise ValueError("Business name cannot be blank")
        self.name = val.strip()
        return self


class BusinessRead(BaseModel):
    id: str
    name: str
    business_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BusinessWithRole(BusinessRead):
    role: str
    can_edit: bool
    can_delete: bool


class BusinessMemberRead(BaseModel):
    id: str
    business_id: str
    user_id: str
    role: str
    can_edit: bool
    can_delete: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StaffInvite(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    can_edit: bool = True
    can_delete: bool = False


class StaffMemberRead(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    can_edit: bool
    can_delete: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StaffUpdatePermissions(BaseModel):
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None


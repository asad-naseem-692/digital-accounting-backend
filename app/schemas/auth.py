from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.schemas.user import UserRead


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    message: str
    # In dev mode, return the reset token directly so testing without email service works
    reset_token: Optional[str] = None


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class MessageResponse(BaseModel):
    message: str

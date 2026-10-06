import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.dependencies.auth import get_current_user
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequestResponse,
)
from app.schemas.user import UserCreate, UserLogin, UserRead

router = APIRouter()


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sign Up (FEAT-01)",
)
def signup(data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user, hash password, and issue JWT."""
    existing_user = db.scalar(select(User).where(User.email == data.email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        name=data.name.strip(),
        email=data.email.lower().strip(),
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign In (FEAT-02)",
)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate with email and password, issue JWT."""
    user = db.scalar(select(User).where(User.email == data.email.lower().strip()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign Out (FEAT-03)",
)
def logout(current_user: User = Depends(get_current_user)):
    """Stateless sign out confirmation."""
    return MessageResponse(message="Signed out successfully")


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Current User Profile",
)
def get_me(current_user: User = Depends(get_current_user)):
    """Return currently authenticated user."""
    return UserRead.model_validate(current_user)


@router.post(
    "/request-reset",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Request Password Reset (FEAT-05)",
)
def request_password_reset(data: PasswordResetRequest, db: Session = Depends(get_db)):
    """Generate a password reset token (returned directly in dev mode)."""
    user = db.scalar(select(User).where(User.email == data.email.lower().strip()))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user found with that email",
        )

    token_str = secrets.token_urlsafe(32)
    reset_entry = PasswordResetToken(
        user_id=user.id,
        token=token_str,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        used=False,
    )
    db.add(reset_entry)
    db.commit()

    return PasswordResetRequestResponse(
        message="Password reset token generated successfully",
        reset_token=token_str,
    )


@router.post(
    "/confirm-reset",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm Password Reset (FEAT-05)",
)
def confirm_password_reset(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Verify reset token and update user password."""
    now = datetime.now(timezone.utc)
    stmt = select(PasswordResetToken).where(
        PasswordResetToken.token == data.token,
        PasswordResetToken.used == False,  # noqa: E712
        PasswordResetToken.expires_at > now,
    )
    reset_entry = db.scalar(stmt)
    if not reset_entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user = db.get(User, reset_entry.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User associated with token not found",
        )

    user.password_hash = hash_password(data.new_password)
    reset_entry.used = True
    db.commit()

    return MessageResponse(message="Password updated successfully")

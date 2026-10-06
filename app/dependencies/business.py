"""
business.py — FEAT-08: Business Scoping Rule

Every business-scoped request must resolve and validate business membership
via the X-Business-Id header on every single request. Never cache or assume.
"""
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.user import User


def get_business_member(
    x_business_id: Optional[str] = Header(None, alias="X-Business-Id"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BusinessMember:
    """
    FEAT-08 core dependency:
    1. Reads X-Business-Id header -> 400 if missing or empty.
    2. Validates business exists and user is an active member -> 403 if not found.
    3. Returns the BusinessMember record with role and permission flags attached.
    """
    if not x_business_id or not x_business_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Business-Id header is required for business-scoped operations",
        )

    business_id = x_business_id.strip()

    stmt = select(BusinessMember).where(
        BusinessMember.business_id == business_id,
        BusinessMember.user_id == current_user.id,
    )
    member = db.scalars(stmt).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this business",
        )

    return member


# Alias for spec naming consistency
get_current_business_membership = get_business_member


def require_can_edit(
    member: BusinessMember = Depends(get_business_member),
) -> BusinessMember:
    """Enforces that the user has edit permission in the active business."""
    if member.role != "owner" and not member.can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action (can_edit required)",
        )
    return member


def require_can_delete(
    member: BusinessMember = Depends(get_business_member),
) -> BusinessMember:
    """Enforces that the user has delete permission in the active business."""
    if member.role != "owner" and not member.can_delete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action (can_delete required)",
        )
    return member


def require_owner(
    member: BusinessMember = Depends(get_business_member),
) -> BusinessMember:
    """Enforces that the user is the owner of the active business."""
    if member.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the business owner can perform this action",
        )
    return member

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password
from app.dependencies.auth import get_current_user
from app.dependencies.business import get_business_member
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.user import User
from app.schemas.business import (
    BusinessCreate,
    BusinessRead,
    BusinessWithRole,
    BusinessMemberRead,
    StaffInvite,
    StaffMemberRead,
    StaffUpdatePermissions,
)

router = APIRouter()


@router.post(
    "",
    response_model=BusinessRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Business (FEAT-06)",
)
def create_business(
    data: BusinessCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new business and register the creator as its owner with full permissions.
    """
    if getattr(current_user, "account_type", "owner") == "staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff accounts are not permitted to register new businesses. Only business owners can create businesses.",
        )

    business = Business(
        name=data.name,
        business_type=data.business_type,
    )
    db.add(business)
    db.flush()  # populate business.id

    membership = BusinessMember(
        business_id=business.id,
        user_id=current_user.id,
        role="owner",
        can_edit=True,
        can_delete=True,
    )
    db.add(membership)
    db.commit()
    db.refresh(business)

    return BusinessRead.model_validate(business)


@router.get(
    "/mine",
    response_model=List[BusinessWithRole],
    status_code=status.HTTP_200_OK,
    summary="List My Businesses (FEAT-07)",
)
def list_my_businesses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return all businesses the authenticated user belongs to (owned or staff),
    along with their role and permission flags in each.
    """
    stmt = (
        select(Business, BusinessMember)
        .join(BusinessMember, Business.id == BusinessMember.business_id)
        .where(BusinessMember.user_id == current_user.id)
        .order_by(Business.created_at.asc())
    )
    results = db.execute(stmt).all()

    items = []
    for business, member in results:
        items.append(
            BusinessWithRole(
                id=business.id,
                name=business.name,
                business_type=business.business_type,
                created_at=business.created_at,
                role=member.role,
                can_edit=member.can_edit,
                can_delete=member.can_delete,
            )
        )
    return items


@router.get(
    "/current",
    response_model=BusinessMemberRead,
    status_code=status.HTTP_200_OK,
    summary="Active Business Membership (FEAT-08)",
)
def get_current_membership(
    member: BusinessMember = Depends(get_business_member),
):
    """
    Returns the resolved membership record for the active business from X-Business-Id.
    Enforces business-scoping validation on the request.
    """
    return BusinessMemberRead.model_validate(member)


def _require_owner(business_id: str, current_user_id: str, db: Session) -> BusinessMember:
    owner = db.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == current_user_id,
        )
    )
    if not owner or owner.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the business owner can view or manage staff access",
        )
    return owner


@router.get(
    "/{business_id}/staff",
    response_model=List[StaffMemberRead],
    status_code=status.HTTP_200_OK,
    summary="List Staff Members (FEAT-25)",
)
def list_staff_members(
    business_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List everyone with access to this business and their permissions."""
    _require_owner(business_id, current_user.id, db)
    stmt = (
        select(BusinessMember, User)
        .join(User, BusinessMember.user_id == User.id)
        .where(BusinessMember.business_id == business_id)
        .order_by(BusinessMember.created_at.asc())
    )
    rows = db.execute(stmt).all()
    results = []
    for member, user in rows:
        results.append(
            StaffMemberRead(
                id=member.id,
                user_id=user.id,
                name=user.name,
                email=user.email,
                role=member.role,
                can_edit=member.can_edit,
                can_delete=member.can_delete,
                created_at=member.created_at,
            )
        )
    return results


@router.post(
    "/{business_id}/staff",
    response_model=StaffMemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite / Add Staff Member (FEAT-24)",
)
def invite_staff_member(
    business_id: str,
    data: StaffInvite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Invite or add a staff member with specified permissions.
    If the email does not exist, registers a new user with temporary credentials.
    """
    _require_owner(business_id, current_user.id, db)
    email_clean = data.email.lower().strip()

    user = db.scalar(select(User).where(User.email == email_clean))
    if not user:
        user = User(
            name=data.name.strip(),
            email=email_clean,
            password_hash=hash_password(data.password),
            account_type="staff",
        )
        db.add(user)
        db.flush()

    existing_member = db.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == user.id,
        )
    )
    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this business",
        )

    membership = BusinessMember(
        business_id=business_id,
        user_id=user.id,
        role="staff",
        can_edit=data.can_edit,
        can_delete=data.can_delete,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)

    return StaffMemberRead(
        id=membership.id,
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=membership.role,
        can_edit=membership.can_edit,
        can_delete=membership.can_delete,
        created_at=membership.created_at,
    )


@router.patch(
    "/{business_id}/staff/{user_id}",
    response_model=StaffMemberRead,
    status_code=status.HTTP_200_OK,
    summary="Update Staff Permissions (FEAT-26)",
)
def update_staff_permissions(
    business_id: str,
    user_id: str,
    data: StaffUpdatePermissions,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update can_edit and can_delete permissions for a staff member."""
    _require_owner(business_id, current_user.id, db)
    target = db.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == user_id,
        )
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")

    if target.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot alter the owner's permissions",
        )

    if data.can_edit is not None:
        target.can_edit = data.can_edit
    if data.can_delete is not None:
        target.can_delete = data.can_delete

    db.commit()
    db.refresh(target)

    user = db.scalar(select(User).where(User.id == target.user_id))
    return StaffMemberRead(
        id=target.id,
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=target.role,
        can_edit=target.can_edit,
        can_delete=target.can_delete,
        created_at=target.created_at,
    )


@router.delete(
    "/{business_id}/staff/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke Staff Access (FEAT-27)",
)
def remove_staff_member(
    business_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke staff member's access to this business immediately."""
    _require_owner(business_id, current_user.id, db)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owners cannot remove themselves from their own business",
        )

    target = db.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == user_id,
        )
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")

    if target.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the owner of the business",
        )

    target_user = db.scalar(select(User).where(User.id == user_id))
    other_memberships = db.scalars(
        select(BusinessMember).where(
            BusinessMember.user_id == user_id,
            BusinessMember.business_id != business_id,
        )
    ).all()

    db.delete(target)

    # If the user was invited as a staff account and has no other businesses,
    # delete their user record entirely so their credentials can NEVER be used
    # to log in or register businesses as an owner.
    if target_user and (getattr(target_user, "account_type", "owner") == "staff" or not other_memberships):
        db.delete(target_user)

    db.commit()
    return {"status": "ok", "message": "Staff member access revoked and credentials disabled successfully"}


from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.business import get_business_member, require_can_edit
from app.models.business_member import BusinessMember
from app.models.product import Product
from app.models.stock_adjustment import StockAdjustment
from app.schemas.product import (
    ProductCreate,
    ProductRead,
    StockAdjustmentCreate,
    StockAdjustmentRead,
)

router = APIRouter()


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add Product (FEAT-21)",
)
def add_product(
    data: ProductCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    """
    Registers a new product in the catalog with optional initial stock.
    """
    if data.sku and data.sku.strip():
        existing_sku = db.scalar(
            select(Product).where(
                Product.business_id == member.business_id,
                Product.sku == data.sku.strip(),
            )
        )
        if existing_sku:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product with SKU '{data.sku.strip()}' already exists",
            )

    product = Product(
        business_id=member.business_id,
        name=data.name.strip(),
        sku=data.sku.strip() if data.sku else None,
        unit_price=data.unit_price,
        cost_price=data.cost_price or 0.0,
        stock_quantity=data.initial_stock or 0,
    )
    db.add(product)
    db.flush()

    if data.initial_stock and data.initial_stock > 0:
        adj = StockAdjustment(
            business_id=member.business_id,
            product_id=product.id,
            change_amount=data.initial_stock,
            reason="Initial stock on product creation",
        )
        db.add(adj)

    db.commit()
    db.refresh(product)
    return ProductRead.model_validate(product)


@router.get(
    "",
    response_model=List[ProductRead],
    status_code=status.HTTP_200_OK,
    summary="View Stock / Catalog (FEAT-22)",
)
def view_stock(
    search: Optional[str] = Query(None),
    low_stock: Optional[bool] = Query(False),
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """
    Lists products for the business. Supports search by name/sku and low_stock filter (<= 5).
    """
    query = select(Product).where(Product.business_id == member.business_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where((Product.name.ilike(term)) | (Product.sku.ilike(term)))

    if low_stock:
        query = query.where(Product.stock_quantity <= 5)

    query = query.order_by(Product.name.asc())
    products = db.scalars(query).all()

    return [ProductRead.model_validate(p) for p in products]


@router.get(
    "/{product_id}",
    response_model=ProductRead,
    status_code=status.HTTP_200_OK,
    summary="Get Product",
)
def get_product(
    product_id: str,
    member: BusinessMember = Depends(get_business_member),
    db: Session = Depends(get_db),
):
    """Get single product details."""
    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.business_id == member.business_id,
        )
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return ProductRead.model_validate(product)


@router.post(
    "/{product_id}/adjust",
    response_model=StockAdjustmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Adjust Stock (FEAT-23)",
)
def adjust_stock(
    product_id: str,
    data: StockAdjustmentCreate,
    member: BusinessMember = Depends(require_can_edit),
    db: Session = Depends(get_db),
):
    """
    Records an immutable stock adjustment and atomically updates product.stock_quantity.
    """
    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.business_id == member.business_id,
        )
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if data.change_amount == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Change amount cannot be zero",
        )

    adjustment = StockAdjustment(
        business_id=member.business_id,
        product_id=product_id,
        change_amount=data.change_amount,
        reason=data.reason.strip(),
    )
    db.add(adjustment)

    # Atomic update
    product.stock_quantity += data.change_amount

    db.commit()
    db.refresh(adjustment)

    return StockAdjustmentRead.model_validate(adjustment)

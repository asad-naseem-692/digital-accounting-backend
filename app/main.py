"""
main.py — FastAPI application factory

Registers all routers, configures CORS, and mounts the /health endpoint.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import (
    auth,
    businesses,
    parties,
    products,
    cash,
    invoices,
    reports,
    transactions,
    staff_book,
)

app = FastAPI(
    title="Digital Accounting / Khata System",
    description="Deterministic full-stack accounting & bookkeeping engine",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health():
    """Returns 200 OK with service status. Used by Railway/load balancers."""
    return {"status": "ok", "environment": settings.environment}


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(businesses.router, prefix="/businesses", tags=["Businesses"])
app.include_router(parties.router, prefix="/parties", tags=["Parties (Customers & Suppliers)"])
app.include_router(products.router, prefix="/products", tags=["Products & Inventory"])
app.include_router(cash.router, prefix="/cash-entries", tags=["Cash Book"])
app.include_router(invoices.router, prefix="/invoices", tags=["Invoicing (Sales & Purchases)"])
app.include_router(transactions.router, prefix="/transactions", tags=["Daily Transactions & Accounting Engine"])
app.include_router(reports.router, prefix="", tags=["Dashboard & Reports"])
app.include_router(staff_book.router, prefix="/staff-book", tags=["Staff Book"])


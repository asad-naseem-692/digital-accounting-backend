# Feature: Adjust Stock (API)
**Owner:** Backend | **Module:** Stock & Inventory

## Goal
Record a stock change with a reason — never edit stock_quantity directly.

## Scope
- Endpoint: `POST /products/{id}/adjust`
- Input: change_amount (+/-), reason (e.g. "Restock", "Sold", "Damaged").
- Creates an immutable `stock_adjustments` row and updates the product's
  current stock_quantity in the same transaction.

# Feature: Update Invoice Status (API)
**Owner:** Backend | **Module:** Invoicing

## Goal
Mark an invoice paid, partially paid, or unpaid.

## Scope
- Endpoint: `PATCH /invoices/{id}/status`
- Allowed: "unpaid" | "partial" | "paid". Business-scoped ownership check.

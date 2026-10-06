# Feature: Create Invoice (API)
**Owner:** Backend | **Module:** Invoicing

## Goal
Let a user generate an invoice/bill for a customer.

## Scope
- Endpoint: `POST /invoices`
- Input: party_id (must be type="customer"), invoice_number
  (auto-generated, sequential per business, e.g. INV-0001), items (array
  of {description, quantity, unit_price} — stored as JSON on the invoice
  row to keep this simple, not a separate table), due_date.
- total_amount computed server-side from items — never trust a
  client-submitted total.
- status defaults to "unpaid".
- Creating an invoice for a customer with items does NOT automatically
  create a ledger transaction (FEAT-11) — that stays a deliberate,
  separate action so users aren't surprised by automatic balance changes.

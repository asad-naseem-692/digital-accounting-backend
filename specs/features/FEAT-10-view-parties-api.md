# Feature: View Parties (API)
**Owner:** Backend | **Module:** Party Ledger (Khata)

## Goal
List all customers/suppliers for the current business, with their
current balance.

## Scope
- Endpoint: `GET /parties` — filtered by business_id.
- Each party includes a computed `current_balance` (sum of their ledger
  transactions) — never a stored/editable field, always derived.
- Optional filter: type=customer|supplier.

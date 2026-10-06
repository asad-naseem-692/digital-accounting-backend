# Feature: Create Party (Customer/Supplier) API
**Owner:** Backend | **Module:** Party Ledger (Khata)

## Goal
Let a user add a new customer or supplier to their business's ledger.

## Scope
- Endpoint: `POST /parties`
- Input: name, type ("customer"|"supplier"), phone (optional),
  opening_balance (optional, positive = they owe you, negative = you owe
  them — recorded as an initial ledger transaction, see FEAT-11).
- Saved with business_id from the scoping dependency.

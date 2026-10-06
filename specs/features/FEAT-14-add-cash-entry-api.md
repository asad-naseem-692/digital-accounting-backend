# Feature: Add Cash Entry (API)
**Owner:** Backend | **Module:** Cash Book

## Goal
Record daily cash movement not tied to a specific party (e.g. shop rent
paid, misc cash sale).

## Scope
- Endpoint: `POST /cash-entries`
- Input: type ("cash_in"|"cash_out"), amount, category (e.g. "Rent",
  "Utilities", "Sales"), description, date.
- Business-scoped. Immutable log (same correction-via-offsetting-entry
  rule as FEAT-11).

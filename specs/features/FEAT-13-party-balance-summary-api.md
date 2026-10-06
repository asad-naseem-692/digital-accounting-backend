# Feature: Party Balance Summary (API)
**Owner:** Backend | **Module:** Party Ledger (Khata)

## Goal
Give a single "how much am I owed / how much do I owe" figure across
all parties.

## Scope
- Endpoint: `GET /parties/summary`
- Returns: total_receivable (sum of positive customer balances),
  total_payable (sum of positive supplier balances owed by us).
- Pure aggregation query, business-scoped.

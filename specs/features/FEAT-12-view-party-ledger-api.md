# Feature: View Party Ledger (API)
**Owner:** Backend | **Module:** Party Ledger (Khata)

## Goal
Show the full transaction history and running balance for one party.

## Scope
- Endpoint: `GET /parties/{id}/transactions`
- Returns transactions ordered by date, each with a computed running
  balance after that entry (like a real ledger/statement).
- Business-scoped + party must belong to the business (404 otherwise).

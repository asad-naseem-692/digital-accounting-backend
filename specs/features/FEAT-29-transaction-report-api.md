# Feature: Transaction Report (API)
**Owner:** Backend | **Module:** Reports & Dashboard

## Goal
Let a user see a combined, filterable report of all financial activity.

## Scope
- Endpoint: `GET /reports/transactions`
- Combines ledger transactions + cash entries into one chronological
  list, filterable by date range and type.
- Business-scoped.

# Feature: View Cash Book (API)
**Owner:** Backend | **Module:** Cash Book

## Goal
List cash entries with running cash-in-hand balance.

## Scope
- Endpoint: `GET /cash-entries`
- Filters: date range, category. Ordered by date, each row shows running
  balance after that entry.

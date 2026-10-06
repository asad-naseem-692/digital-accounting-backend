# Feature: Cash-in-Hand Summary (API)
**Owner:** Backend | **Module:** Cash Book

## Goal
Give the current total cash-in-hand figure at a glance.

## Scope
- Endpoint: `GET /cash-entries/summary`
- Returns: current cash_in_hand (sum of all cash_in minus all cash_out),
  today's cash_in, today's cash_out. Business-scoped.

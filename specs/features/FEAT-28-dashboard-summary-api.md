# Feature: Dashboard Summary (API)
**Owner:** Backend | **Module:** Reports & Dashboard

## Goal
Give a one-glance view of the business's financial health.

## Scope
- Endpoint: `GET /dashboard/summary`
- Returns: cash_in_hand (from FEAT-16), total_receivable, total_payable
  (from FEAT-13), today's cash_in/cash_out, count of unpaid invoices,
  count of low-stock products.
- Pure aggregation of existing data — no new business logic.

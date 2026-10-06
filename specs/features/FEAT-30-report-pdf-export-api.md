# Feature: Report PDF Export (API)
**Owner:** Backend | **Module:** Reports & Dashboard

## Goal
Let a user download a shareable PDF report (e.g. for a bank, partner,
or accountant).

## Scope
- Endpoint: `GET /reports/transactions/pdf`
- Same filters as FEAT-29, rendered as a clean PDF (business name, date
  range, transaction table, summary totals). Deterministic template,
  no AI.

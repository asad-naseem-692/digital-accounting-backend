# Feature: Invoice PDF Export (API)
**Owner:** Backend | **Module:** Invoicing

## Goal
Let a user download/share a clean PDF of an invoice.

## Scope
- Endpoint: `GET /invoices/{id}/pdf`
- Generates a PDF (e.g. via a Python PDF library) showing business name,
  invoice number, party details, itemized list, total, due date.
- No AI involved — a deterministic template-based PDF render.

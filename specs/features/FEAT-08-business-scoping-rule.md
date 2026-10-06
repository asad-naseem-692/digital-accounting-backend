# Feature: Business Scoping (Cross-Cutting Rule)
**Owner:** Backend | **Module:** Auth & Business

## Goal
Guarantee no request ever reads or writes another business's data, and
that a user can only act within a business they're actually a member of.

## Scope
- Not a single endpoint — a mandatory rule for every other feature in
  this system. Every business-scoped endpoint requires an
  `X-Business-Id` header/param, and a dependency
  (`get_current_business_membership`) that:
  1. Confirms `current_user.id` has a `business_members` row for that
     business_id (403 otherwise).
  2. Exposes the user's role/permissions in that business for
     permission checks (FEAT-24-27).
- Every query (parties, ledger transactions, cash entries, invoices,
  products, staff) MUST filter by `business_id` from this dependency —
  document this as a mandatory checklist item for every other feature.

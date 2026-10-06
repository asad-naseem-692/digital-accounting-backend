# Feature: Create Business (API)
**Owner:** Backend | **Module:** Auth & Business

## Goal
Let a user set up a new business (their shop/company) to manage.

## Scope
- Endpoint: `POST /businesses`
- Input: business_name, business_type (optional, e.g. "Retail", "Services").
- Creates a `businesses` row, then a `business_members` row linking the
  creator as role="owner" with full permissions.

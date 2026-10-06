# Feature: List My Businesses (API)
**Owner:** Backend | **Module:** Auth & Business

## Goal
Let a user see every business they own or are staff on, to switch
between them.

## Scope
- Endpoint: `GET /businesses/mine`
- Returns businesses joined through `business_members` for
  `current_user.id`, with the user's role in each.

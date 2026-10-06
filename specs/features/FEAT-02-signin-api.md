# Feature: Sign In (API)
**Owner:** Backend | **Module:** Auth & Business

## Goal
Verify credentials and issue an access token.

## Scope
- Endpoint: `POST /auth/login`
- Verify bcrypt hash. Issue JWT containing user id only (role/business
  context is resolved per-request via FEAT-08, since one user can belong
  to multiple businesses with different roles in each).
- Generic "invalid email or password" error.

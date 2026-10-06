# Feature: JWT Token Generation & Verification
**Owner:** Backend | **Module:** Auth & Business

## Goal
Issue and verify tokens.

## Scope
- `create_access_token(user_id)` / `decode_access_token(token)`.
- `get_current_user` dependency — business context is NOT in the token;
  it comes from a required `X-Business-Id` header (or path param) on
  every business-scoped request, checked against FEAT-08's membership
  table on every single request.

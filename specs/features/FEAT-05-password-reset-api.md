# Feature: Password Reset (API)
**Owner:** Backend | **Module:** Auth & Business

## Goal
Let a user securely reset a forgotten password.

## Scope
- `POST /auth/request-reset` — short-lived single-use token (dev mode:
  return/log it, no real email service).
- `POST /auth/confirm-reset` — verify token, bcrypt-hash new password.

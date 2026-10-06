# Feature: Sign Up (API)
**Owner:** Backend | **Module:** Auth & Business

## Goal
Let a new user create an account (a user, not tied to any business yet).

## Scope
- Endpoint: `POST /auth/signup`
- Input: name, email, password.
- Hash with bcrypt. Save to `users` table. Return created user (never
  password hash). Note: creating a business is a separate step (FEAT-06)
  — a user can exist without owning a business yet.

# Feature: Invite Staff (API)
**Owner:** Backend | **Module:** Staff & Permissions

## Goal
Let a business owner add a staff member with limited access.

## Scope
- Endpoint: `POST /businesses/{id}/staff` (owner only, 403 otherwise).
- Input: name, email, temporary password (simple flow — no email
  service; owner sets a temp password directly, staff resets it later
  via FEAT-05), can_edit (bool), can_delete (bool).
- Creates a `users` row if the email doesn't exist yet, then a
  `business_members` row with role="staff" and the given permissions.

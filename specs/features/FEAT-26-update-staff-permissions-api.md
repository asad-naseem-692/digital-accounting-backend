# Feature: Update Staff Permissions (API)
**Owner:** Backend | **Module:** Staff & Permissions

## Goal
Let an owner change what a staff member can do.

## Scope
- Endpoint: `PATCH /businesses/{id}/staff/{user_id}`
- Input: can_edit, can_delete (bool flags). Owner only.
- These flags are checked by FEAT-08's dependency on every
  create/update/delete request across the whole system — not just
  documented, actually enforced everywhere.

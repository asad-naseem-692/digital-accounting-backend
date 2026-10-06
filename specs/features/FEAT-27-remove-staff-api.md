# Feature: Remove Staff (API)
**Owner:** Backend | **Module:** Staff & Permissions

## Goal
Revoke a staff member's access to this business.

## Scope
- Endpoint: `DELETE /businesses/{id}/staff/{user_id}` (owner only).
- Deletes the `business_members` row only — does NOT delete the user's
  account globally (they may have access to other businesses, or none).
- An owner cannot remove themselves this way (self-action prevention).

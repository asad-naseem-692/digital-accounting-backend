# Feature: View Staff (API)
**Owner:** Backend | **Module:** Staff & Permissions

## Goal
List everyone with access to this business.

## Scope
- Endpoint: `GET /businesses/{id}/staff` (owner only).
- Returns each member's name, email, role, permissions, joined date.

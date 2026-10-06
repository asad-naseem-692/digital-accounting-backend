# Feature: Add Ledger Transaction (API)
**Owner:** Backend | **Module:** Party Ledger (Khata)

## Goal
Record a "you gave" or "you got" entry against a party — the core Khata
action.

## Scope
- Endpoint: `POST /parties/{id}/transactions`
- Input: type ("credit"|"debit" — "credit" = they now owe you more /
  you gave them goods on credit; "debit" = they paid you / you received
  money), amount, description, date.
- Immutable log — never edit/delete a transaction directly; a correction
  is a new offsetting transaction (document this rule clearly).
- Records `created_by = current_user.id`.

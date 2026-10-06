# AGENTS.md — Backend (FastAPI) — Digital Accounting / Khata System

## Scope
This file applies to the `backend/` folder only. Deploys to Railway with
a Postgres database. A sibling `frontend/AGENTS.md` covers the frontend —
do not build any UI here.

## Tech stack (do not substitute)
Python, FastAPI, Pydantic v2, SQLAlchemy + Alembic, PostgreSQL,
python-jose (JWT), passlib[bcrypt] (password hashing), a PDF generation
library (e.g. `reportlab` or `weasyprint` — pick one, document the
choice) for invoice/report exports.

## No AI in this project
Unlike our other projects, this system uses **no AI/LLM at all** — it's
a deterministic bookkeeping/accounting application, same as the real
apps that inspired it (digital ledger apps). Do not add any AI
dependency (no OpenAI/Gemini SDK) unless explicitly asked later.

## Python project manager: use `uv`, not pip/requirements.txt
Same as our other projects: `uv init`, `uv add <package>`, commit
`pyproject.toml` + `uv.lock` (no `requirements.txt`). Run via
`uv run uvicorn app.main:app --reload`. Remember: set
`[tool.uv] package = false` in `pyproject.toml`, or the Railway build
will fail expecting a `src/<name>/__init__.py` package layout.

## Build order — full-stack, one feature at a time
Vertical slices pairing backend + frontend specs, one feature at a time,
stop for approval after each. Follow `specs/features/` in `FEAT-XX`
numeric order. Suggested module order: Auth & Business → Party Ledger →
Cash Book → Invoicing → Stock → Staff & Permissions → Reports & Dashboard.

## Core architectural invariant
This backend is the single source of truth. All authorization,
business-scoping, and permission enforcement happen here — never trust
the frontend. **Every business-scoped request must resolve and validate
business membership via the `X-Business-Id` header on every single
request** (see FEAT-08) — there is no shortcut or cached assumption.

## Hard rules
- **Ledger transactions, cash entries, and stock adjustments are
  immutable logs** — never update or delete a past entry. A correction
  is always a new, offsetting entry. This preserves an honest audit
  trail, same principle as a real accounting ledger.
- Balances (party balance, cash-in-hand, stock quantity) are always
  **derived/computed from the transaction log**, never stored as a
  directly-editable field that could drift out of sync with reality.
- A user can belong to multiple businesses with different roles in each
  — role/permissions are never assumed from a JWT claim alone, always
  re-checked against `business_members` for the specific business in
  the request.
- `can_edit` / `can_delete` permission flags (for staff) are enforced on
  every relevant write endpoint — not just hidden in the UI.
- Invoice totals are always computed server-side from line items —
  never trust a client-submitted total.
- `DATABASE_URL`, `CORS_ORIGINS`, and `JWT_SECRET_KEY` always come from
  environment variables via a central `app/core/config.py` — never
  hardcoded.
- Never combine `allow_origins=["*"]` with `allow_credentials=True`.
- Passwords always hashed with bcrypt — never logged or returned in
  plain text.

## Database — local only for now
For this phase, we are using a **local PostgreSQL instance** (managed
via pgAdmin on the developer's machine) — not Railway. Do NOT set up any
Railway database or ask for a Railway connection string. I will provide
a local `DATABASE_URL` (something like
`postgresql://postgres:PASSWORD@localhost:5432/accounting_db`) — put it
directly in the local `.env` file, never hardcode it in any committed file.
We will move to a hosted database later when we're ready to deploy —
don't build anything that assumes a specific hosting provider; just read
`DATABASE_URL` from the environment as usual.

## Deployment — not yet
Do NOT deploy this project (no Railway service, no Vercel project) at
this stage. Build and run everything locally (`uv run uvicorn
app.main:app --reload`), verify locally, and we'll deploy once the
feature set is far enough along. Still write the `Dockerfile` as part of
scaffolding (per "What you set up yourself" below) so it's ready when we
do deploy, but don't act on it yet.

## Data dictionary — return exactly these field names, always
`snake_case` fields, ISO 8601 UTC timestamps, UUID string ids, errors as
`{ "detail": "message" }`, list endpoints return plain arrays.

- **User**: `id, name, email, created_at`
- **Auth response**: `{ "access_token": string, "token_type": "bearer", "user": User }`
- **Business**: `id, name, business_type, created_at`
- **BusinessMember**: `id, business_id, user_id, role ("owner"|"staff"), can_edit, can_delete, created_at`
- **Party**: `id, business_id, name, type ("customer"|"supplier"), phone, current_balance (computed), created_at`
- **LedgerTransaction**: `id, business_id, party_id, type ("credit"|"debit"), amount, description, date, created_by, created_at`
- **CashEntry**: `id, business_id, type ("cash_in"|"cash_out"), amount, category, description, date, created_by, created_at`
- **Invoice**: `id, business_id, party_id, invoice_number, items (json array of {description, quantity, unit_price}), total_amount, status ("unpaid"|"partial"|"paid"), due_date, created_at`
- **Product**: `id, business_id, name, sku, unit_price, stock_quantity (computed), created_at`
- **StockAdjustment**: `id, business_id, product_id, change_amount, reason, created_at`

If a feature needs a field not listed here, use the same conventions and
flag it in your summary — add it to both `backend/AGENTS.md` and
`frontend/AGENTS.md`. Never invent or rename a field silently on one side.

## Keep specs and code in sync (mandatory, every time)
The spec file for a feature is the source of truth for what that feature
is supposed to do — not just a one-time planning document. Whenever you
add, change, or remove behavior in a feature after it's already been
built:
1. **Update that feature's `.md` file in `specs/features/` in the same
   change** — add/edit/remove the relevant bullet points (endpoint path,
   request/response shape, validation rule, permission rule) so the spec
   still accurately describes the current behavior.
2. If the change affects what the frontend receives (new/renamed field,
   changed endpoint, changed status codes), note that clearly in the
   spec so it's visible to whoever is working on the frontend repo.
3. If a change doesn't fit any existing feature file, create a new
   `FEAT-XX-name.md` for it, following the same format as the others,
   rather than leaving the change undocumented.
4. Never let a spec describe behavior that no longer exists in the code,
   and never let the code do something its spec doesn't mention. Treat a
   stale or missing spec update as an incomplete task, not an optional
   cleanup step.

## Never let a change to one feature break a feature it depends on
Many features here depend on the business-scoping rule (FEAT-08) and the
immutable-ledger pattern. Before changing a feature others rely on,
check `specs/features/` for anything referencing it. If a change is
genuinely needed — including anything affecting the API contract the
frontend depends on — update that feature's spec explicitly and confirm
nothing else breaks. Never modify a dependency's code, spec, or a fixed
rule (like "ledger entries are immutable") silently as a side effect of
unrelated work.

## What you set up yourself
`.env.example` / local `.env` (`DATABASE_URL`, `CORS_ORIGINS`,
`JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`ENVIRONMENT`), `.gitignore` (must ignore `.env`, `.venv/`,
`__pycache__/`, but NOT `uv.lock`), `pyproject.toml` + `uv.lock`,
`Dockerfile` (installs `uv`, runs `uv sync --frozen`, listens on
Railway's `$PORT`), central `app/core/config.py`, a `/health` endpoint,
a seed script creating one demo business with a few parties/products so
the app isn't empty on first login.

## Deployment target (later)
Railway (backend + Postgres) once we're ready — not yet, see "Deployment
— not yet" above.

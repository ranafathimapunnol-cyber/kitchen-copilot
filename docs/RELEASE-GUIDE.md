# Kitchen Copilot — Release and Operations Guide (Stage 13)

Status: prepared 26 November 2026. **Nothing here has been deployed.** The
hosting provider (proposal: AWS) and the production attachment storage
(decision D9) are not chosen yet, so this guide describes the release
package and the checks, not a live environment.

## 1. What is released

| Part | Folder | Runs as |
|---|---|---|
| Web application (Next.js 16) | `apps/web` | `next start` (Docker image `apps/web/Dockerfile`) |
| API (FastAPI) | `services/api` | `uvicorn app.main:app` (Docker image `services/api/Dockerfile`) |
| Database | PostgreSQL 16 (pgvector image) | 15 migrations, head `c4d7e9a1f203` (a 16th, `d5e8f0b2a314` for SUPER_ADMIN, is held until authorized) |
| Reverse proxy | `infra/nginx/default.conf` | nginx in front of web and API |

Kitchen Copilot (the agent) runs inside the API process. It is **off**
unless `AGENT_ENABLED=true` (section 5).

## 2. Configuration (names only — never commit values)

API (`services/api/.env` or the host's secret store):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection |
| `SECRET_KEY` | Token signing; long and random; rotating it signs everyone out |
| `FRONTEND_BASE_URL` | Origin used in password setup/reset links |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM` | Password emails (setup, reset, Admin invitations) |
| `APP_TIMEZONE` | Campus business dates (default `Asia/Kolkata`) |
| `ATTACHMENT_STORAGE_BACKEND`, `ATTACHMENT_STORAGE_DIR` | Bill attachments (production backend: decision D9) |
| `AGENT_ENABLED` | Kitchen Copilot on/off (default `false`) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Optional external model for reading requests only |
| `AGENT_PROCEDURES_DIR` | Folder of approved procedure documents (Markdown) |
| `AGENT_PROPOSAL_TTL_HOURS` | Pending proposals expire after this (default 72) |

Web: `NEXT_PUBLIC_API_BASE_URL` at build time.

## 3. Release checklist

1. Backend tests: the full suite in the one-off compose container
   (`docs/DEVELOPMENT-SAFETY.md` §3.3). All must pass.
2. Frontend: `npx tsc --noEmit`, `npx eslint`, `npm test`, `npx next build`.
3. Migration graph: one head (`tests/test_migration_graph.py`).
4. Back up the target database and verify the backup (section 4).
5. Rehearse the migration on a restored copy (upgrade, downgrade, upgrade;
   compare every table) before the real apply.
6. Apply migrations once: `alembic upgrade head` (the API image runs this on
   start in `compose.yaml`; on a shared server run it once by hand first).
7. Smoke test as each role (ADMIN, KITCHEN_MANAGER, STAFF; SUPER_ADMIN only
   once migration `d5e8f0b2a314` is applied):
   sign in, dashboard, one list per module, one report export, Copilot
   status.
8. Record the release (version, migration head, test counts) in
   `docs/REMAINING-WORK.md`. Mark nothing ACCEPTED without the client.

## 4. Backup and restore

Backups: `docs/DEVELOPMENT-SAFETY.md` §4.1 (pg_dump `-Fc`), verified per
§4.3 (restore into a network-isolated, in-memory container and compare row
counts). Keep at least the last daily seven and the pre-release dump, outside
the repository, readable only by the operator. Bill attachments are files:
back up `ATTACHMENT_STORAGE_DIR` together with the database dump.

Restore (into an empty database of the same major version):

```bash
pg_restore -d <empty database> --no-owner --no-privileges --exit-on-error <dump file>
```

Then start the API (it runs `alembic upgrade head`, which does nothing when
the dump is already at head) and run the smoke test (step 7).

The stock ledger is append-only (database triggers refuse UPDATE, DELETE
and TRUNCATE on `stock_movements`); a restore recreates the triggers from
the dump. Never disable them to "fix" data: post a reversal.

## 5. Turning on Kitchen Copilot

1. Set `AGENT_ENABLED=true` and restart the API.
2. Without `GEMINI_API_KEY` the agent reads requests with its built-in
   rules (no network). With a key, the model receives only the request text,
   today's date and the campus's meal session, menu and item names — never
   amounts, stock, suppliers or people — and every figure still comes from
   the application.
3. Approved procedure documents: put each as a Markdown file in
   `AGENT_PROCEDURES_DIR`. With none, the agent says procedure guidance is
   unavailable from the approved sources.
4. Every request, tool call, proposal, approval and result is stored
   (`agent_*` tables) and the decisions are also in the audit log.

## 6. First platform owner (SUPER_ADMIN)

**Available only after migration `d5e8f0b2a314` (M1) is authorized and
applied**; the script ships with it. Then run once on the server, with SMTP
configured:

```bash
python -m scripts.create_super_admin "Full Name" owner@example.org
```

The account has no campus and no usable password; a setup link is emailed.
The SUPER_ADMIN then creates organisations and campuses and invites each
campus's first Admin from **Organisations & Campuses**.

## 7. Interim rules in force (pending client answers)

| Question | Interim behaviour |
|---|---|
| Q4 (AT03 transaction count) | One transaction = one supplier bill; purchase days = distinct bill dates |
| Q5 (bill-level discounts/charges) | Not shared out to items in price comparisons |
| Q6 (supplier credits) | PUR05 supplier returns and credits not released |
| Q19 (sign-in lock-out) | 5 failed sign-ins per email or 30 per IP in 15 minutes → wait (HTTP 429) |
| C5 / Q2 (Stage 7 items) | Not released |
| ADR-005 (separate Actions service) | Agent actions run in the API process through the same validated services, with approval, permission re-check and audit (`docs/STAGE-10-12-NOTES.md`) |
| ADR-009 (MongoDB traces) | Agent traces in PostgreSQL JSON, as ADR-009 allows for low volume |

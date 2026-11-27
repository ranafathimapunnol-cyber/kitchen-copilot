# Kitchen Copilot — Remaining Work Checklist

Prepared 18 November 2026; **updated 24 November 2026** after Stages 4–6,
Stage 7 S7-A and Stage 8a were built and tested. Sources: `PROPOSAL.md`
(§5, §7, §13, §14, §17.2), `REQUIREMENTS-TRACEABILITY.md`,
`BACKEND-COMPLETION-PLAN.md` (C1–C10, D1–D10, M1–M12), `CLIENT-QUESTIONS.md`,
`diagrams/ERD.md`, the stage plans and the ADRs. Statuses come from
`REQUIREMENTS-TRACEABILITY.md`; this file is the work plan, not evidence.
Estimates are developer-days for one developer and include backend,
screens, migration, tests and documentation.

Question numbers (Q1–Q22) are `PROPOSAL.md` §17.2. C/D numbers are
`BACKEND-COMPLETION-PLAN.md`. Row numbers (#) are kept from the first
version of this file because other documents refer to them.

**Nothing is ACCEPTED** (no client walkthrough yet) and **nothing is
DEPLOYED** (no public or production deployment exists).

## Client-acceptance readiness (27 November 2026)

| Status | Count | Rows |
|---|---|---|
| TESTED | 41 | every other requirement, AT01–AT08, and the cross-cutting rows except authorisation |
| IN_PROGRESS | 4 | PUR03 (client answer: several receipts per purchase, §4.3); STK01 and OUT03 (supplier returns, need PUR05 / Q6); four-role authorisation (SUPER_ADMIN migration `d5e8f0b2a314` awaiting authorization) |
| PENDING | 1 | PUR05 (Q6) |
| ACCEPTED | 0 | no client walkthrough yet |
| DEPLOYED | 0 | no hosting chosen (Q17/Q18) |

Ready for a client walkthrough: every TESTED row, on the development
site. Rows marked "interim" (Q4, Q5, Q19, C5 matching, ADR-005/009
deviations) need the client to confirm or replace the interim rule during
the walkthrough. Not ready: the five open rows above, which wait for
client answers or approval, not for development.

27 November work: Kitchen Copilot review on realistic data (eight defects
fixed, `STAGE-10-12-NOTES.md`); release guide now covers `COOKIE_SECURE`,
client addresses behind nginx (required before release; see
`RELEASE-GUIDE.md` §2) and the unapproved Gemini key.

## Update 26 November 2026 (Stages 9, 10, 12, 13 preparation)

| Row | Stage | Result |
|---|---|---|
| 9 | Stage 9 dashboard and reports | DASH01–DASH05, AT03 (interim Q4), AT07, report export TESTED; home dashboard rebuilt |
| 10 | Stage 10 audit, security, users | Audit Log, User Accounts, Account Security screens; sign-in throttling (interim Q19); session revocation — TESTED |
| 12 | Stage 12 Kitchen Copilot | Chat, plan, tool trace, proposals, approve/reject with permission re-check and audit — TESTED with the built-in reader and FakeLLM; `AGENT_ENABLED=false` by default; no live model key |
| 11 | Stage 11 SUPER_ADMIN | Prepared and tested (migration `d5e8f0b2a314`, 3 tests, round trip 18/18), **not applied** — awaiting authorization |
| 13 | Stage 13 release | `RELEASE-GUIDE.md` written; nothing deployed |

- Database: migration `c4d7e9a1f203` (M7) applied to the development
  database on 26 Nov 2026; backup
  `~/kitchen-copilot-backups/pre-c4d7e9a1f203-20261126-210339` (verified, 49
  table-data entries); existing rows, STAFF grants, permissions and ledger
  triggers unchanged (before/after fingerprints identical).
- Tests: full backend suite 767 passed (Stages 10–12 together); Stage 10+12
  targeted suites 154 passed; M7 round trip 14/14; frontend type check,
  lint, 85 unit tests and production build clean.
- Prototype pages `/status` and `/streaming` removed.
- Live check on http://localhost:3001 (ADMIN, KITCHEN_MANAGER, STAFF; desktop
  and phone): 29 of 29. STAFF #3 holds an older `audit.read` grant (no
  longer assignable), so it can read the Audit Log; removing it needs approval.
- Still blocked: row 4 (Q6), Stage 7 S7-B (C5) and S7-C (Q2), procedure
  documents for the agent (Q21), external LLM use, hosting (Q17/Q18), D9.

## Status summary (24 November 2026)

| Status | Count | Requirements |
|---|---|---|
| TESTED | 30 | PUR01, PUR02, PUR04; STK02, STK03, STK04, STK05; MEAL01–MEAL05; PLAN01–PLAN08; OUT01, OUT02; AT01, AT02, AT04, AT05, AT06, AT08; authentication; campus isolation |
| IN_PROGRESS | 8 | PUR03 (client answer on multiple receipts per purchase, §4.3); STK01 (supplier returns in the ledger, needs PUR05 / Q6); OUT03 (criteria 2–4, Q6); four roles (SUPER_ADMIN, row 11); audit (viewer, row 10); reports — export and print (every §5.8 report, row 9); security (row 10, Q19); AI (row 12) |
| PENDING | 8 | PUR05 (Q6); DASH01–DASH05; AT03 (Q4); AT07 |
| ACCEPTED | 0 | — |
| DEPLOYED | 0 | — |

## Built and TESTED (not yet ACCEPTED)

| # | Stage | Migration (applied to the Docker development database) | Requirements |
|---|---|---|---|
| — | Authentication, sessions, campus isolation; master data screens; waste tracking; STAFF permission assignment | earlier migrations | Authentication, campus isolation TESTED |
| — | PUR01 bill attachments and duplicate invoices; PUR02 bill totals; PUR04 payments and balances (AT08) | `e7b3c5a19d42` (18 Nov 2026) | PUR01, PUR02, PUR04, AT08 TESTED |
| 1 | Receipts screens (18 Nov 2026) | — | PUR03 IN_PROGRESS (client confirmation on multiple receipts per purchase) |
| 3 | Purchase orders and the `purchase_bill.*` split (20 Nov 2026) | `a3c9e1f47b20` | PUR03 criterion 2 (ordered quantities) |
| 2 | **Stage 4** stock ledger: opening stock, balances, low stock, replenishment, item ledger (4a); kitchen issues, unused returns, reversals, append-only ledger (4b); blind counts and independently approved adjustments (4c) (`STAGE-4-STOCK-PLAN.md`) | `b5e1d7c3a920`, `c7d2e9f4a816`, `0e7d99065bd3` (23 Nov 2026) | STK02–STK05, AT01, AT02 TESTED; STK01 IN_PROGRESS (supplier returns, Q6) |
| 7 | **Stage 5** meal records: headcounts, prepared dishes, distribution, leftovers, reconciliation, interim retained-food carry-forward, linked issues and usage, close / cancel / reopen (`STAGE-5-MEAL-PLAN.md`) | `ea00e5387c2f` (23 Nov 2026) | MEAL01–MEAL05 TESTED |
| 6 | **Stage 6** meal planning: item kind, versioned portion standards, suggestions from past meals, meal plans with recalculation, overrides, stock gap, approval snapshot, cancel and replace, plan versus actual (`STAGE-6-PLANNING-PLAN.md`) | `f3a8c2d61b47` (24 Nov 2026) | PLAN01–PLAN08, AT05, AT06 TESTED |
| 5 (part) | **Stage 7 S7-A** search-as-you-type item and supplier pickers in every entry form and filter (`STAGE-7-READINESS-ASSESSMENT.md`) | none (frontend only) | no requirement ID (§5.7); tested |
| 8 (part) | **Stage 8a** outsourced food: orders, deliveries (received, rejected, accepted), received lines on meal records, bill-line links, stock guards, report with Excel, PDF and print (`STAGE-8-IMPLEMENTATION-PLAN.md` §12, interim rules listed there) | `b8e4c2a9d175` (24 Nov 2026) | OUT01, OUT02, AT04 TESTED; OUT03 IN_PROGRESS |

## Remaining, in dependency order

| # | Stage | Requirements | Needs | Blocked by (client dependencies) | Days |
|---|---|---|---|---|---|
| 4 | **Stage 8b** supplier returns and credits | PUR05; OUT03 criteria 2–4; STK01 criterion 3 (supplier returns in the ledger) | Stages 4 and 8a (built); possibly a migration for `supplier_returns` | **Q6** (on hold by standing rule) | 3–4.5 |
| 5 | **Stage 7, rest** | S7-B duplicate meal sessions on campus 1 ("Breakfast" / "breakfast", "early morning") and optional session codes (migration M3); S7-C master-data permission codes; optional S7-D to S7-H | — | C5 (four or five sessions); Q2 (who edits master data); Q7/Q8 for S7-E | 1–1.5 (+ optional items) |
| 9 | **Stage 9** dashboard and reports | DASH01–DASH05, AT03, AT07, every §5.8 report with Excel, PDF and print. Also found in the 24 Nov readiness review: the home dashboard predates Stages 4–8 (quick links and figures cover only older modules), and its headcount figure reads `daily_headcounts`, which has no entry screen, while meal records hold the real headcounts | Stages 4–8a (built) | Q4 (what counts as one chicken purchase, AT03); §7 which reports Accounts and Kitchen Managers need — interim definitions possible | 11–14 |
| 10 | **Stage 10** audit, security, users | Audit viewer; login throttling and session revocation; user management screens | — | Q19 session and recovery policy | 4–5 |
| 11 | **Stage 11** organization and campus administration | SUPER_ADMIN, organizations, campuses, role and permission management | Migrations M1, M8 | C1/D1 role-model documents; M1 needs its own explicit authorization. Can follow launch if one organization is enough at first | 6–9 |
| 12 | **Stage 12** AI agent — approved scope (`PROPOSAL.md` §7): three jobs — (1) plan and procure, (2) explain spending, (3) investigate a stock difference; permission-checked and campus-scoped tools, application calculations only, drafts and proposals with human approval, traceability, FakeLLM test path, `AGENT_ENABLED=false` by default | Today only prototypes exist (`spikes/ai`: tool calling with FakeLLM and Gemini, pgvector retrieval, streaming; `spikes/actions`). Not yet in place: migration M12 (agent runs, steps, proposals), Celery and Redis (ADR-004), the Flask actions service (ADR-005), MongoDB traces (ADR-009) | Job 1: Stage 6 and purchase orders (built). Job 2: Stage 9 price and quantity decomposition. Job 3: Stage 4c counts (built); supplier returns (8b) for full coverage | Q20 who may use each job; Q21 procedures approved for retrieval; Q22 approval process; external LLM use permitted (`CLIENT-QUESTIONS.md` §8) — without it only FakeLLM can run | 23–30 |
| 13 | **Stage 13** release | Full regression, backup and restore drill, deployment guide, training, AT01–AT08 client walkthroughs; commit and review of the Stage 3–8a work; refreshed Docker images (see below) | Everything above | Q14 retention, RPO and RTO; Q17/Q18 hosting; D9 attachment storage provider; no public deployment without approval | 14–21 |

**Totals** (24 November 2026, from the rows above): to a releasable
application without row 11: about **56–76 days** (rows 4, 5, 9, 10, 12, 13);
with row 11: about **62–85 days**. Rows that cannot start until the client
answers: 4 (Q6) and the blocked parts of 5. Row 12 can be built and tested
with FakeLLM before the AI questions are answered, but cannot run a live
model until external LLM use is approved.

## Current state of the development environment (24 November 2026)

- **Database:** Docker PostgreSQL `kitchen_copilot_db` on port 5433 at
  migration `b8e4c2a9d175` (head of 14 migrations; 48 tables, 186 foreign
  keys). The Homebrew PostgreSQL on port 5432 is not used.
- **Backups:** a verified pre-migration dump for every migration applied
  since 18 November in `~/kitchen-copilot-backups` (all 18 dumps read back on
  24 Nov 2026), and a full local recovery copy of the repository, the
  current database and every backup in
  `~/kitchen-copilot-recovery/20261124-200620`. Both are on this laptop only.
- **Version control:** the Stage 3–8a work (including 8 of the 14 migration
  files) is not yet committed; branch `p0-baseline`.
- **Running application:** API on the host at `http://localhost:8000`
  (`uvicorn --reload`, latest source, Docker database); frontend production
  build of the latest source at `http://localhost:3001` (bound to this Mac
  only; API base `http://localhost:8000`).
- **Out-of-date Docker services (left unchanged):** the Compose `web`
  container on port 3000 runs an image built 14 November with the API base
  `http://localhost:8080` baked in; the Compose `api` container has been
  stopped since 17 November; `nginx` (port 8080) restarts continuously
  because the `api` host does not exist while that container is stopped. Do
  not start the old `api` image: its start command runs
  `alembic upgrade head` with its own, older migration files. Rebuilding the
  images needs approval.

## Test results (24 November 2026)

- Backend: 735 tests. Full PostgreSQL suite twice (734 passed each; the one
  test added afterwards passed separately); PostgreSQL-only files five
  times (99 passed each). M6 round trip on an empty database (20 checks) and
  on a copy of the development data (50 checks); the API end to end on the
  copy (33 checks).
- Frontend: 81 unit tests; type check, lint and production build clean.
- Browser (production builds): Stage 8a 66; purchasing 64 / 62 / 26 / 25 /
  35 / 57 / 42; Stage 4a 55, 4b 48, 4c 57; meals 54; planning 51; S7-A
  pickers 41; readiness sweep of all 47 screens at 1440 px and 390 px.
- Port 8000 read-only smoke tests: Stage 8a 19, planning 40, meals 26,
  counts 27, kitchen 24, stock 23, Stage 3 54.
- Live site (`http://localhost:3001` → `http://localhost:8000` → Docker
  database), read-only browser check: 104 of 104 — login form reaches the
  API (a wrong password is refused); every screen for ADMIN at 1440 px and
  390 px with no page or API errors; Kitchen Manager, STAFF #3, STAFF #9
  and the campus 2 Admin see exactly what their roles and grants allow;
  database write counters unchanged.

## Infrastructure items outside the requirement list

- D9: production attachment storage provider (S3-compatible) and its
  client library.
- A persistent attachment folder (Docker volume) for the Docker API.
- Generated API types (`apps/web/src/types/api.ts`) were regenerated in
  Stages 5, 6 and 8a and are identical to a generation from the running API
  (130 paths, 24 November 2026).
- Port 8000 development API: repointed to the Docker database on port
  5433 on 18 November 2026 (`.env` backed up first; smoke test 13 of 13).
- Prototype pages `/status` and `/streaming`: removed 26 November 2026.

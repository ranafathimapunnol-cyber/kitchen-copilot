# Kitchen Copilot — Backend Completion Assessment and Five-Day Plan

| | |
|---|---|
| Status | **Proposed. Awaiting approval. No implementation has started.** |
| Assessed | 17 November 2026 |
| Branch / commit | `p0-baseline` at `b97b810`, plus uncommitted work (UI redesign, ADMIN password management, CORS) |
| Method | Static inspection of every route, model, migration, test and document; safe offline test runs only |
| Database | Not contacted. No migration created or run. `.env` not read or changed |

---

## 0. Summary

- **Done and tested offline:** authentication (including ADMIN password setup and reset), campus isolation, master data (categories, units, conversions, items, suppliers, meal sessions, menus), staff permission assignment, goods receipts that post stock once, supplier bill entry, waste tracking, and a role-gated dashboard.
- **Not started:** most of the approved operational scope. That includes stock issues, returns, counts and adjustments; payments and supplier returns; meal records, preparation, distribution and leftovers; outsourced food; meal planning and versioned standards; purchase orders; dashboard analytics; reports and exports; and every ERD §8 module.
- **Almost all remaining work needs new tables or columns**, so it depends on migration approval.
- **Estimated remaining effort for the approved Must scope** (excluding AI and the ERD-only modules) is about **25 backend developer-days and 13 frontend developer-days**. Adding SUPER_ADMIN, the ERD-only modules and AI brings it to about 55.
- **Verdict:** completing everything in five working days is **not realistic**. Section 7 commits to a defined subset (the stock and purchasing backbone, meal planning, the dashboard comparison and core reports), and even that depends on approvals on Day 1.

---

## 1. Baseline captured before this assessment

Saved outside the repository at
`/private/tmp/claude-501/-Users-ismailpunnol-Desktop-kitchen-copilot/836f47e5-ecfd-484f-a2bd-6fcdde332ef5/scratchpad/pre-assessment-snapshot.txt`.

| Item | Value |
|---|---|
| Branch / HEAD | `p0-baseline` / `b97b810` |
| Uncommitted | 21 modified files, 27 untracked paths (UI redesign, password management, CORS). Nothing reset, stashed or discarded |
| Protected files (sha256) | `suppliers/page.tsx` c4840d95…; `test_purchases.py` 846e56fb…; `spikes/ai/test_spikes.py` 56f2b155… — none modified |
| Migrations | 6 files, unchanged, single head `d4e8a91b2c70` |
| `.env` | Untracked and git-ignored; last modified 10 Nov; contents not read |
| `AGENT_ENABLED` | `False` (default in `app/core/config.py`) |

### Tests actually run today (offline, no PostgreSQL)

Every run used a deliberately unreachable `DATABASE_URL`, so any accidental connection would fail instead of reaching a database.

| Run | Result |
|---|---|
| `pytest --noconftest` on `test_migration_graph.py` and `test_password_management.py` | **48 passed** |
| Offline SQLite harness over the 11 other test modules (runs each test function directly, without the project's `conftest.py`) | **161 passed, 0 failed** |
| PostgreSQL test suite | **Not run.** Has not been run since commit `b97b810`. Requires your approval |

> Correction: earlier reports gave the harness result as "141 passed". The per-module counts (20, 15, 13, 24, 38, 6, 10, 7, 7, 8, 13) add up to **161**. The tests did not change; the earlier total was mis-added.

**What "verified" means in this document:** automated tests exist and passed in the offline runs above. Nothing is verified against PostgreSQL yet.

---

## 2. Requirement-source conflicts (not resolved; your decision needed)

These stop specific items. None has been resolved in code or in this plan.

| # | Conflict | Evidence | Effect |
|---|---|---|---|
| C1 | **Four different role sets.** The proposal and client notes approve **Admin, Kitchen Manager, Store Keeper, Accounts** (05 Nov). The code has **ADMIN, KITCHEN_MANAGER, STAFF**. Your brief names **SUPER_ADMIN, ADMIN, KITCHEN_MANAGER, STAFF** | `PROPOSAL.md` §4.1–4.2, §17.1; `client-notes.md` §1; `models/user.py`; ERD §1 | Every role-dependent item: user management, permissions, stock approvals, financial reports |
| C2 | **The Stage 2 architecture, Stage 3 roadmap and four-role SUPER_ADMIN/ADMIN/KM/STAFF matrix are not in the repository.** The only trace is ERD §8 | Searched all `.md`, `.py`, `.ts`, `.json` and `.yaml` files | ERD §8 is used below as the target design. The exact permission matrix cannot be verified |
| C3 | **STAFF permission mapping cannot be established from repository documents.** No document defines STAFF. The code has a 15-code assignable list (`STAFF_ASSIGNABLE_PERMISSIONS`, added in fix B) and keeps older non-assignable grants unchanged | `dependencies.py` lines 74–96; ERD §5 | **Stopped.** No mapping changed or proposed. Legacy grants can't be listed without querying the database, which is not allowed |
| C4 | **Purchase-order permission codes.** `purchase_order.*` currently guards supplier bills (`/api/purchases`). A real purchase-order module needs codes Kitchen Managers can hold without seeing bills | `purchases.py`; `dependencies.py` lines 18–26 | Purchase orders are blocked. Any fix changes what existing permission rows mean, which needs approval |
| C5 | **Number of meal sessions.** The proposal has four (breakfast, lunch, snacks, dinner). ERD §8 has "five canonical meal sessions via a session code" | `PROPOSAL.md` MEAL01; ERD §8 | Meal-session codes and meal records |
| C6 | **Expiry and lots.** ERD §8 adds expiry flags and lots. The proposal lists "Expiry and batch tracking" as **Won't have** | `PROPOSAL.md` §11.4; ERD §8 | Item and stock schema |
| C7 | **Duplicate invoices.** PUR01 says duplicates must be **flagged for review**. The code and a database unique constraint **reject** them (409) | `purchases.py`; ERD §4 | Changing to flagging means dropping a constraint (a migration) |
| C8 | **Supplier page vs. navigation.** The backend gives Kitchen Managers read-only supplier access. The protected `suppliers/page.tsx` is ADMIN-only, while the sidebar shows the link to anyone with `inventory.read` | `permissions.ts`; protected file | Kitchen Managers see a link that bounces them. Fixing it needs either the protected file or the access rules changed |
| C9 | **Scope of the ERD-only modules.** Tasks, attendance, hygiene, supplier intelligence and full alerts appear only in ERD §8, not in the proposal's Must list or release plan | `PROPOSAL.md` §11, §15; ERD §8 | Priority P3 below until you confirm they belong in this phase |
| C10 | **AI is Must in the proposal** (all three agent jobs) but was scheduled for its own week (Week 4) | `PROPOSAL.md` §11.1, §15 | Cannot fit this week. Proposed for deferral |

---

## 3. Completion matrix

**Priority:**
- **P0:** decision or prerequisite that blocks other work
- **P1:** Must, and on an acceptance-test path (AT01–AT08)
- **P2:** Must, but not on an acceptance-test path
- **P3:** ERD §8 only, or a later phase

**Effort:** developer-days including backend tests; "BE" is backend, "FE" is frontend. These are planning estimates, not commitments.

| Module | Approved requirement | Current implementation | Missing work | Dependencies | Priority | Estimated effort | Status |
|---|---|---|---|---|---|---|---|
| Authentication | §13: cookie JWT, refresh, CSRF, no public registration. ERD §8: invitations, revocable sessions, password reset, login throttling | Login, refresh, logout, CSRF. ADMIN email invite, setup and reset; every session invalidated when the password changes; rate limits on password endpoints. UI done. Tests: auth 7, password 42 (passing) | Login throttling. Logout does not revoke tokens. Recovery for Kitchen Managers and Staff (§17.2 Q19). Rate limits need uvicorn proxy headers behind nginx | Q19 | P2 | BE 0.5d | Partially implemented |
| User management | §4.3: only Admin creates users; users cannot change roles | ADMIN creates KM/STAFF in their own campus (role allow-list, audited). Staff list and detail. ADMINs created through the operator CLI. Tests: user_creation 15 (passing). UI: Staff page covers STAFF only | List every campus user including Kitchen Managers; edit; deactivate and reactivate; admin-started reset for Kitchen Managers and Staff | C1 | P1 | BE 0.75d · FE 0.5d | Partially implemented |
| Organization and campus management | ERD §8 and your brief: a SUPER_ADMIN with no campus manages organizations, campuses and ADMIN provisioning | `campuses` table only. No API. No SUPER_ADMIN | Organizations; `campuses.organization_id`; SUPER_ADMIN; campus endpoints; ADMIN provisioning endpoint (can reuse `provision_admin`) | Migration M1 plus explicit SUPER_ADMIN authorization; C1 | P0 to decide, P2 to build | BE 1.5d · FE 1d | Blocked (approval) |
| Role and permission management | Approved matrix. ERD §8: `role_permissions` table; new actions DELETE, APPROVE, EXPORT, RECORD | ADMIN has every code. Kitchen Manager set fixed in code (20 codes). STAFF assignment API and UI with 15 assignable codes; older grants kept. Kitchen Managers read-only on suppliers. Tests: authorization 38, staff 20, KM 13 (passing) | `role_permissions` table; APPROVE, EXPORT and RECORD actions; the authoritative matrix document; how Store Keeper and Accounts duties map | C1, C2, C3, M8 | P0 | BE 1d | Partially implemented (blocked by C1–C3) |
| Dashboard | DASH01–05: filters, spend, % change, highest-spend categories, price rises, price vs. quantity split, like-for-like units, elapsed-day comparison, drill-down | Role-gated overview: KPIs, 7-day headcount and waste-cost trends, recent records, audit feed. UI with charts. Tests: 6 (passing) | Everything in DASH01–05: filter parameters, weighted average prices, "Not comparable", elapsed-day ranges, drill-down with permission checks | Purchase data and conversions already exist. **DASH01–04 need no migration** | P1 (AT07) | BE 1.5d · FE 1d | Partially implemented |
| Headcount | MEAL01: per date and session, expected students, staff and guests recorded separately; actual people served recorded separately | `daily_headcounts` (date and student count only), read by the dashboard. No API, no UI | Per-session expected counts by group and actual served; record and update endpoints; UI | M5 (or a student-only API on the existing table now) | P1 (feeds AT05) | BE 0.75d · FE 0.5d | Partially implemented |
| Inventory (items) | §5.7: name, category, **kind** (raw, prepared or outsourced), base unit, minimum stock, active | Item CRUD; base unit locked once referenced. UI done; tests passing | `item_kind`. Expiry flags only if C6 is resolved in favour of the ERD | M3, C6 | P1 | BE 0.25d · FE 0.25d | Partially implemented |
| Categories and units | §5.7, ADR-007 | CRUD, deactivate, ADMIN-only delete, dimension locked once referenced. UI done. Tests: master_data and integrity (passing) | None | None | — | — | Implemented and verified |
| Unit conversions | ADR-007 and ledger rules: explicit, dimension-compatible, historical factors preserved | CRUD, dimension checks, frozen once used, one conversion per unit pair. UI done; tests passing | Item-specific conversions (for example weight to pieces for one item) are not modelled | §17.2 Q8 | P2 | BE 0.5d (if approved) | Implemented and verified |
| Suppliers | §4.2 matrix plus your decision: Kitchen Managers read-only | CRUD; Kitchen Manager writes rejected (403). UI is ADMIN-only (protected file). Tests passing | Navigation vs. page mismatch (C8). The Accounts role doesn't exist | C1, C8 | P2 | FE 0.25d | Implemented and verified |
| Menus and portion standards | PLAN02, PLAN06: per-person standards by menu; raw vs. prepared; versions with effective dates; approval; one-day overrides with a reason | Menu CRUD. `menu_main_items` holds per-person quantities with unit validation. UI done; tests passing | Versioned standards (effective date, version, approver), overrides, preserved history | M3/M4; §17.2 Q3 (who approves) | P1 (AT06) | BE 1d · FE 0.5d | Partially implemented |
| Meal sessions | MEAL01: breakfast, lunch, snacks, dinner | CRUD; UI done; tests passing | Session codes, if C5 is decided | C5, M3 | P2 | BE 0.25d | Implemented and verified (target design open) |
| Meal plans | PLAN01–08 | Nothing | Plans and lines that snapshot the standard used; recalculation; procurement gap = max(0, required − current stock); overrides; no stock effect; plan vs. actual; suggestions from history (PLAN03) | M4; stock balances; versioned standards | P1 (AT05, AT06) | BE 2d · FE 1d | Not implemented |
| Purchase orders | Your decision and ERD §8: real purchase orders with an ORDERED state; Kitchen Managers create, read and update them without seeing bills | Nothing. `purchase_order.*` codes guard **bills** | Order tables; order → bill → receipt links; separate permission codes | **C4** plus M7 | P1 | BE 1.5d · FE 1d | Blocked (approval) |
| Supplier bills (`/api/purchases`) | PUR01/02: lines, exact decimal totals, attachments, duplicate flagging, originals preserved | Create (always DRAFT) with lines, totals, conversion checks; duplicate invoice rejected (409); list and detail; audited; Kitchen Managers blocked. Tests: 7 (passing). **No UI** | Attachments (ADR-008); posting, cancellation and corrections; flagging duplicates instead of rejecting (C7); UI | ADR-008 storage provider; Q5; M7 | P1 (AT08) | BE 1.5d · FE 1d | Partially implemented |
| Supplier payments | PUR04: full and partial payments, balances, supplier summaries | `supplier_payments` table exists. No API, UI or tests | Payment endpoints; payment ≤ outstanding; balances; supplier summaries; audit | **No migration needed**; Q6 (credits) | P1 (AT08) | BE 0.75d · FE 0.5d | Not implemented |
| Supplier returns and credits | PUR05, OUT03 | `supplier_returns` and return-line tables exist. No API | Return endpoints; credit notes; stock outflow; effect on what is owed | Ledger direction and source key (M2); Q6 | P1 | BE 1d | Not implemented |
| Goods receipts | PUR03 | Draft then accept. Only accepted quantities post stock, once (database unique key); conversions applied. Tests: 8 (passing). **No UI** | Ordered quantity (needs purchase orders); cancel or reverse a receipt; UI | Purchase orders; M2 | P1 (AT01) | BE 0.5d · FE 0.75d | Partially implemented |
| Stock (ledger, balances, counts, adjustments) | STK01, STK04, STK05; ADR-006 | `stock_movements` holds receipts only; list endpoint. No balances, opening stock, counts or adjustments | Direction, effective time, unique source key, reversal link; opening stock; balances, low-stock and replenishment lists; counts that snapshot the system balance; adjustments approved by someone other than the counter; negative-stock rule | M2; Q9 (negative stock); Q10 (no independent approver) | P1 (AT01, AT02) | BE 2.5d · FE 1.5d | Partially implemented |
| Consumption (kitchen issues and unused returns) | STK02, STK03 | Only the `consumption.*` codes exist; no endpoint uses them | Issue and return tables; returns linked to their issue; stock posting; net usage | M2; confirm that "consumption" means issues and returns | P1 (AT01) | BE 1.5d · FE 1d | Not implemented |
| Waste tracking | As-built module. ERD §6: raw-ingredient waste posts stock once confirmed; prepared-food waste never does | CRUD with type, stage and reason rules; audited; delete is ADMIN-only. Tests: 13 (passing). UI done | Confirmation state; raw-waste stock posting | M11, M2 | P2 | BE 0.5d | Partially implemented |
| Prepared food | MEAL02–05: dishes, distribution, leftovers, reconciliation | Nothing | Dish, distribution and leftover tables; available = distributed + remaining | M5; §17.2 Q11 | P2 | BE 2d · FE 1d | Not implemented |
| Outsourced food | OUT01–03; AT04 | Only the `outsourced_food.*` codes exist | Orders linked to bills; received, distributed and leftover quantities; rejected deliveries; report | M6; Q6; links to purchase orders and bills | P1 (AT04) | BE 1.5d · FE 1d | Not implemented |
| Tasks | ERD §8: Pending, Completed, Postponed | Nothing | Table, endpoints, UI | M9; C9 | P3 | BE 0.75d · FE 0.5d | Not implemented |
| Attendance | ERD §8: staff attendance. The proposal excludes *student* attendance | Nothing | Table, endpoints, UI | M9; C9 | P3 | BE 0.75d · FE 0.5d | Not implemented |
| Hygiene | ERD §8: hygiene and uniform checks | Nothing | Table, endpoints, UI | M9; C9 | P3 | BE 0.75d · FE 0.5d | Not implemented |
| Supplier intelligence | ERD §8: supplier metrics | Nothing | Price trends, delivery reliability (needs receipts and returns data) | Payments, returns, purchase orders; C9 | P3 | BE 1d · FE 0.5d | Not implemented |
| Alerts | STK04 low-stock (proposal). ERD §8: alerts with recipients, actions and delivery history | Nothing. The email sender now exists | Low-stock list (P1, comes with STK04); alert tables; delivery | M10 for full alerts | P1 for low stock, P3 for the rest | BE 0.5d + 1.5d | Not implemented |
| Reports and exports | §5.8 report list; Excel, PDF and print; AT03, AT04, AT08 | Dashboard only. No report endpoints. No export library installed | Report endpoints showing period, filters and units; CSV (no new dependency); Excel and PDF | **New dependency (D6)**; Q4 (what counts as one chicken purchase) | P1 (AT03, AT08) | BE 2.5d · FE 1d | Not implemented |
| Audit logs | §13: actor, action, record, before and after values, time, approval, source; written in the same transaction | Written in the same transaction for users, staff access, master data, bills, receipts, waste and passwords. Read only through the dashboard feed | Read and filter endpoint (`audit.read`); consistent before and after values; approval fields | None | P2 | BE 0.75d · FE 0.5d | Partially implemented |
| AI integration | §7: three agent jobs, controlled tools, retrieval, actions service, approvals | `AGENT_ENABLED=False`. Prototypes only (`spikes/ai` FakeLLM streaming, `spikes/actions`). No `services/actions` | All of it | Most modules above; M12; MongoDB, Celery, Redis | P3 this week | BE 5d+ | Not implemented (proposed deferral, C10) |

### Cross-cutting findings

- **Campus isolation** is applied in every route inspected (each query filters by the user's campus). Covered by the authorization tests.
- **Security items to fix:**
  - Password rate limits see nginx's address for every user unless uvicorn runs with `--proxy-headers --forwarded-allow-ips=<nginx address>`.
  - Login answers faster for unknown emails, because it skips the password check. That timing gap could reveal which emails have accounts.
  - Logout does not revoke tokens. They expire on their own, or immediately on a password change.
- **No frontend screens** exist for bills, receipts, stock, headcount, payments, reports or audit.

---

## 4. Schema changes that need migration approval

**Proposed only. Nothing below has been created.** Every migration would be additive and preserve existing records, migrations and primary keys, per ERD §8.

| Bundle | Purpose | Tables and columns (proposed) | Unblocks | Gate |
|---|---|---|---|---|
| M1 | Platform | `organizations`; `campuses.organization_id`; `SUPER_ADMIN` added to the `userrole` enum; `users.campus_id` and `audit_logs.campus_id` made nullable, with a check that only SUPER_ADMIN may have no campus | Organizations, campuses, SUPER_ADMIN | **Separate explicit authorization** (your standing rule) |
| M2 | Stock ledger | `stock_movements`: direction, `effective_at`, unique `source_key`, `reversal_of_id`. New tables: `kitchen_issues` + lines, `kitchen_returns` + lines, `stock_counts` + lines (system balance snapshot), `stock_adjustments` (`counted_by` ≠ `approved_by`) | STK01–05, AT01, AT02, supplier returns, waste posting | Approval; Q9, Q10 |
| M3 | Master data | `items.item_kind`; meal-session code (C5); expiry flags only if C6 allows | Items, sessions | Approval; C5, C6 |
| M4 | Planning | `portion_standards` (versioned: effective date, approver); `meal_plans`, `meal_plan_lines` (snapshot of the standard used), overrides with reason | PLAN01–08, AT05, AT06 | Approval. Moving existing `menu_main_items` rows into versioned standards would change existing records and needs its own approval |
| M5 | Meals | `meal_records` (expected students, staff and guests; actual served), `prepared_dishes`, `distributions`, `leftovers` | MEAL01–05 | Approval; Q11 |
| M6 | Outsourced | `outsourced_orders` + lines, linked to bills | OUT01–03, AT04 | Approval; Q6 |
| M7 | Purchasing | `purchase_orders` + lines (ORDERED); `bill_files` (ADR-008); allowed bill status values; separate permission codes for bills and orders | Purchase orders, bill attachments | Approval; **C4 changes the meaning of existing permission rows** |
| M8 | Permissions | `role_permissions`; permission actions extended with DELETE, APPROVE, EXPORT and RECORD | Role management | Approval; C1–C3 |
| M9 | People and operations | `tasks`, `staff_attendance`, `hygiene_checks` | P3 modules | C9 |
| M10 | Insight | `alerts`, `alert_recipients`, `alert_deliveries` | Full alerts | C9 |
| M11 | Waste | `waste_records.status` (draft or confirmed) | Raw-waste stock posting | Approval |
| M12 | AI | Agent run, step and proposal tables | AI | Deferred (C10) |

### Buildable now with no schema change

- Supplier payments and balances
- Stock balance, low-stock and replenishment lists (from today's receipt-only ledger)
- Audit read endpoint
- Listing and deactivating users
- Login throttling
- A student-only headcount endpoint
- DASH01–04 analytics
- Purchase reports (AT03, vegetables, supplier balances) as JSON and CSV
- Bill posting and cancellation (the status column is free text)

---

## 5. Approvals and decisions needed from you

| # | Decision | Recommended default (applies only if you approve it) |
|---|---|---|
| D1 | Which role model is authoritative (C1). Please add the Stage 2, Stage 3 and four-role matrix documents to `docs/` (C2) | Keep the code's three roles until the documents are in the repo; add SUPER_ADMIN via M1 when authorized |
| D2 | STAFF assignable mapping (C3) | No change: keep the current 15-code list and the older grants as they are |
| D3 | Purchase-order and bill permission codes (C4) | New `supplier_bill.*` codes for bills, keeping `purchase_order.*` for real orders. This needs a data migration that **reassigns existing grants**, which must be reviewed row by row |
| D4 | Migration bundles M2–M7 and M11 (plus M1 separately) | Approve M2 and M4 first (they cover four acceptance tests) |
| D5 | Scope of the ERD-only modules (C9) and AI deferral (C10) | Defer both beyond this week |
| D6 | Export dependencies (for example `openpyxl` for Excel and a PDF library) | CSV this week; Excel and PDF only if approved |
| D7 | Business rules: Q4 (chicken transaction), Q5 (discount allocation), Q6 (credits), Q9 (negative stock), Q10 (no independent approver), Q11 (retained leftovers), Q3 (who approves standards) | Q9: block issues that exceed stock. Q10: no fallback; the adjustment waits. Others: keep discounts and credits separate, with no allocation |
| D8 | Running the PostgreSQL test suite in Docker, per `DEVELOPMENT-SAFETY.md` §3.3 | Approve once, before any migration work |
| D9 | Bill attachment storage provider (ADR-008) | Local file adapter in development; choose the provider before production |
| D10 | Meal sessions: four or five (C5); expiry and lots (C6); duplicate invoices: flag or reject (C7); supplier page fix (C8) | Four sessions; no expiry or lots (proposal Won't-have); keep rejecting duplicates (stricter); fix C8 via an approved edit to the protected file |

---

## 6. Effort and feasibility

| Scope | Backend | Frontend | Total |
|---|---|---|---|
| Approved Must scope, excluding AI, SUPER_ADMIN and ERD-only modules | ~25.5 d | ~13 d | ~40 d (including ~1.5 d PostgreSQL verification and documentation) |
| + SUPER_ADMIN, organizations, campuses | 1.5 d | 1 d | +2.5 d |
| + ERD-only modules (tasks, attendance, hygiene, supplier intelligence, full alerts) | 4.75 d | 2.5 d | +7.25 d |
| + AI (three agent jobs, actions service) | 5 d+ | 1 d+ | +6 d+ |
| **Everything** | | | **~55 developer-days** |

Five working days is roughly a tenth of the full scope. Even allowing for a large speed-up from AI-assisted implementation, the full scope is several weeks of work. The proposal's own release plan spread the same scope over Weeks 2 to 5.

**What can realistically be committed this week:** the backend for the stock and purchasing backbone, meal planning, dashboard comparison and core reports (section 7), with screens only for the most important flows. Even that relies on approvals D1, D4, D7 and D8 arriving on Day 1 and has no slack. If migrations are not approved on Day 1, the week shrinks to the "buildable now" list in section 4.

**Acceptance tests reachable by the end of the week** (with Day 1 approvals):
- AT01, AT02, AT05, AT06 and AT07
- AT03 and AT08 depend on Q4 and on exports (D6); CSV is possible without D6
- **AT04 is not reachable this week**, because outsourced food is deferred

---

## 7. Five-day execution plan (re-scoped)

Each day has **Commit** items, which the day is judged on, and **Stretch** items, attempted only if Commit is done. Every day ends with offline tests passing, and with a PostgreSQL run if D8 is approved.

### Day 1 — Approvals, verification baseline, and work that needs no migration

| | Work |
|---|---|
| Morning | Your decisions D1–D8. If D8 is approved: run the full PostgreSQL suite once to get a real baseline for everything uncommitted |
| Commit | 1. Stock balance, low-stock and replenishment service and endpoints (STK04) built on the existing ledger. 2. Supplier payment endpoints: payment ≤ outstanding, bill balances, supplier summaries, audited (PUR04). 3. Audit read endpoint with filters (`audit.read`) |
| Commit (if D4) | Write and review migration M2, then upgrade the **test** database only |
| Stretch | List, deactivate and reactivate users; login throttling; uvicorn proxy-header setting |
| Gate | New isolated tests passing; harness still 161/161; migration graph shows one head |

### Day 2 — Kitchen planning (M3 and M4)

| | Work |
|---|---|
| Commit | `item_kind`; versioned portion standards (effective dates, approver, history preserved); meal plans (PLAN01, 02, 04, 06, 07): recalculation, snapshotted standards, overrides with a reason, **no stock movement**; procurement gap against current stock (PLAN05) |
| Targets | **AT05** (rice 67.5 kg and chicken 90 kg for 450 people; recalculates; no stock change) and **AT06** |
| Stretch | Per-session headcount (`meal_records`, M5 part 1); plan-vs-actual skeleton (PLAN08) |

### Day 3 — Stock workflows and purchasing (M2 and M7)

| | Work |
|---|---|
| Commit | Ledger direction, effective time, source key and reversals; opening stock; kitchen issues and unused returns linked to their issue, with net usage (STK01–03); physical counts snapshotting the system balance, and adjustments that the counter cannot approve (STK05) |
| Targets | **AT01** (a receipt adds stock exactly once, an issue reduces it, a return restores it, the ledger equals the shown balance) and **AT02** |
| Stretch | Supplier returns and credits (PUR05); bill posting and cancellation; purchase orders, if D3 is decided; raw-waste stock posting (M11) |

### Day 4 — Dashboard analytics and reports

| | Work |
|---|---|
| Commit | DASH01–04: filters, weighted average price, price vs. quantity split, "Not comparable", elapsed-day ranges; reports with period, filters and units: chicken summary (AT03), supplier balances and payments (AT08), stock movements and low stock; CSV export |
| Targets | **AT07**; AT03 and AT08 at CSV level |
| Stretch | Excel and PDF (if D6); vegetable report; plan-vs-actual report; DASH05 drill-down |
| Not this week | Prepared food, outsourced food, tasks, attendance, hygiene, supplier intelligence, full alerts. ERD §8 scope does not fit; see section 8 |

### Day 5 — Integration and final verification

| | Work |
|---|---|
| Commit | Full PostgreSQL suite plus migration upgrade and downgrade on the test database (D8); authorization regression across every new endpoint for each role; security review (rate-limit proxy headers, login timing, new endpoints' campus scope); minimum screens for stock balances, issues and returns, count approval, payments and meal plans; update the ERD, `REQUIREMENTS-TRACEABILITY.md` and this plan |
| Stretch | Remaining screens; bill and receipt screens |
| Exit | An honest status per requirement ID, every claim backed by a test run |

---

## 8. Deferred beyond this week (unless scope changes elsewhere)

- Purchase orders, if D3 is not decided by Day 3
- MEAL02–05 (preparation, distribution, leftovers)
- OUT01–03 and AT04
- DASH05
- Bill attachments (D9)
- SUPER_ADMIN, organizations and campus management (M1)
- Role-permissions table (M8)
- Tasks, attendance, hygiene, supplier intelligence and full alerts (C9)
- AI (C10)
- Excel and PDF, if D6 is not approved
- Screens for most new endpoints

---

## 9. Test plan

"Now" means it runs offline today: isolated SQLite tests with `--noconftest`, a mocked mailer and an unreachable `DATABASE_URL`. "PG" means it needs the PostgreSQL run (D8).

| Feature | Unit | API | Authorization | Validation and errors | Needs PostgreSQL | Frontend checks |
|---|---|---|---|---|---|---|
| Stock balances and low stock | Balance from ledger; below-minimum rule | List and filter balances; replenishment list | `inventory.read` per role; campus isolation | Unknown item 404; inactive items | Numeric precision; aggregate performance | Balance screen totals match API (Now: tsc, lint, build) |
| Supplier payments | Outstanding = total − payments; decimal rounding | Create and list; supplier summary | Kitchen Manager denied (bill data); ADMIN allowed | Payment > outstanding 422; amount ≤ 0 422; other campus's bill 404 | Concurrent payments (row lock); `amount > 0` check | Payment form, balance display |
| Audit read | Filter building | Paginated, filtered list | `audit.read` only; campus isolation | Bad date range 422 | — | Audit page |
| Versioned standards and meal plans | Required = headcount × standard; rounding counts up; gram/kilogram display | Create, edit and recalculate a plan | Who approves (Q3); STAFF read-only | Missing standard; incompatible units | Historical snapshot persists (AT06); no stock rows written (AT05) | Plan screen recalculates live |
| Ledger, issues, returns | Sign by movement type; net usage | Issue, return, opening, reversal | Store Keeper / STAFF duties (C1, C3) | Over-issue blocked (Q9); a return without its issue 422 | Unique `source_key` blocks double posting; atomic posting with audit (ADR-010) | AT01 walkthrough |
| Counts and adjustments | Snapshot of system balance; difference | Count, then propose an adjustment, then approve it | Approver ≠ counter; ADMIN and KM only | Self-approval 403; count changed after the fact 409 | Concurrent approvals | AT02 walkthrough |
| Dashboard analytics | Weighted average price; price vs. quantity split; "Not comparable"; elapsed days | Filters | Financial figures hidden from Kitchen Managers | Zero or missing previous period | Large date ranges | AT07 figures match the API |
| Reports and CSV | Totals; units shown | Report endpoints; CSV download | Financial reports ADMIN only (C1) | Bad period 422 | Totals match on-screen figures (AT08) | Export keeps the filters |
| Migrations M2–M7 | — | — | — | — | **Upgrade and downgrade on the test database only; migration graph keeps one head (Now)** | — |

Every new feature also gets an isolated test file in the style of `tests/test_password_management.py`. It runs offline now, and also runs under the full suite.

---

## 10. Recommended first task for Day 1

**Supplier payments and balances (PUR04).**

- The table already exists, so **no migration is needed**.
- It is on the AT08 path and is Must scope.
- It has clear arithmetic rules that can be tested offline today.
- It doesn't depend on the role decision (ADMIN allowed, Kitchen Manager denied, matching the current bill restriction).

Build it while D1–D8 are being decided. Stock balances (STK04) come next, for the same reasons.

---

*This document was the only file created by the assessment. No code, migrations, database records, permissions, `.env` or protected files were changed.*

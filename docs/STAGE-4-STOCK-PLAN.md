# Stage 4 — Stock Ledger (STK01–STK05, AT01, AT02): Implementation Plan

Prepared 20 November 2026, after Stage 3 was TESTED. Decisions S1–S7 and
the interim behaviour for client questions Q9 and Q10 were **approved on
23 November 2026** (section 4). This is a plan, not evidence; statuses
stay in `REQUIREMENTS-TRACEABILITY.md`. Slices 4a, 4b and 4c were built
on 23 November 2026 (section 6). Items marked **Client** wait for the
client and are not built on a guess.

Sources: `PROPOSAL.md` §4.2 (permission matrix), §5.2 (STK01–STK05), AT01,
AT02, §17.2 (Q4, Q9, Q10); `client-notes.md` §3 and §5;
`CLIENT-QUESTIONS.md` §1 and §3; `specs/LEDGER-AND-UNIT-RULES.md`;
ADR-006 (immutable ledger), ADR-007 (units), ADR-010 (approval
transactions); `BACKEND-COMPLETION-PLAN.md` (M2, D7).

## 1. What exists today

- `stock_movements` holds goods-receipt postings only: type `RECEIPT`,
  positive quantity in the item's standard unit, one row per receipt line
  (unique per campus), source = the goods receipt. Read-only log screen at
  `/dashboard/stock-movements`. On 23 November 2026 the development
  database held 6 such rows across 2 campuses (read-only check; revision
  `a3c9e1f47b20`).
- `items.minimum_stock` exists (standard unit). Units and campus
  conversions exist, with a converter through the item's standard unit.
- `meal_sessions` and `menus` (each menu belongs to a meal session) exist.
  There are no meal records yet (MEAL01–MEAL05 are Stage 7).
- Permission modules `inventory.*` (receipts, stock reading; create and
  update not assignable to STAFF) and `consumption.*` (STAFF-assignable,
  used by nothing yet).

## 2. Approved rules this plan follows (no decision needed)

- Balances are calculated from posted movements only; posted movements are
  never edited or deleted; corrections are reversals or approved
  adjustments (STK01, ADR-006).
- Stock balance = opening + receipts + unused returns − kitchen issues −
  supplier returns ± approved adjustments and reversals (§5.2).
- Draft issues do not change stock; confirmed issues reduce it; confirmed
  unused returns increase it and reference their issue; net usage = issued
  − returned (STK02, STK03).
- **Issues that exceed available stock are refused** (STK04 criterion 4,
  approved). The proposal's exception, "unless an authorized correction
  resolves the shortage", is met by recording the missing receipt or an
  approved adjustment first; no override is built (see Q9 below).
- A count keeps the system balance at count time, the physical quantity
  and the difference, with date, verifier and reason; the count itself is
  never changed; any adjustment is a separate movement (STK05).
- Adjustments are approved by an ADMIN or KITCHEN_MANAGER who did not
  perform the count; STAFF (the Store Keeper duties) never approve
  (§4.2, `client-notes.md` §3).
- Every posting is atomic with its audit row and cannot be posted twice
  (ADR-010).
- Quantities are exact decimals; entered quantities are converted to the
  item's standard unit through explicit conversions only, and the factor
  used is stored on the line (ADR-007).

## 3. Open client questions that affect this stage

The questions stay open with the client. Only the behaviour built
meanwhile was approved on 23 November 2026.

| Ref | Question | What is built meanwhile |
|---|---|---|
| **Q9** / §3.1 | Should negative stock ever be allowed? | No balance goes below zero by any path. Over-issues are refused (approved STK04 criterion) and every other path is refused too (S2). |
| **Q9** / §3.2 | How are emergency issues recorded (food used before its receipt is entered)? | **Not built** (interim option a). No override and no "waiting for stock" issue. A draft issue can be saved at any time, but it is confirmed only once the receipt is recorded and accepted. Options for the client: (a) never allowed; (b) ADMIN/KM may confirm with a reason, the balance goes negative and is flagged until a receipt or adjustment clears it (needs a flag column and a dashboard alert); (c) a "waiting for stock" issue confirmed once the receipt is accepted (needs an extra status); (d) an emergency receipt without a bill (changes PUR03, where every receipt belongs to a bill). Go-live risk: friction if kitchens record receipts late. |
| **Q10** | Who approves an adjustment when no eligible independent approver exists? | **No fallback** (interim option a). The adjustment stays PENDING until an ADMIN or KM who did not count approves it, and the screen says why. Campus 1 currently has one active ADMIN and one active KITCHEN_MANAGER, so a count by either can be approved by the other; it waits only while that person is away. Options for the client: (a) wait; (b) an ADMIN approves their own count with a reason and a "self-approved" flag in audit and reports (breaks the approved independence rule, so needs the client's sign-off); (c) a SUPER_ADMIN approves (Stage 11). |
| §3.4 / Q4 | How are physical stock differences handled (tolerances, reason categories, recount)? | Every difference is shown; an adjustment is raised only by an explicit action, never automatically; free-text reason required; no tolerance or auto-approval. |
| §1.2–1.3 | One store or several per campus; transfers between stores? | One ledger per campus, as today. No store dimension and no transfers. If the client has several stores, the ledger needs a store column (a later migration). |
| §3.3 / Q7–Q8 | Units and conversions per item | Uses the conversions entered in master data; a missing conversion is refused, never assumed. |

## 4. Decisions (approved 23 November 2026)

All nine recommendations were approved as presented: S1–S7 and the
interim behaviour for Q9 and Q10 (section 3). They bind Stage 4; changing
any of them needs a new decision.

### S1 — Permissions

| Action | Guarded by | STAFF-assignable |
|---|---|---|
| Kitchen issues and unused returns | existing `consumption.*`: `create` = record a draft; `update` = edit, cancel or confirm a draft; `read` = view | Yes (already) |
| Physical counts | new module `stock_count`: `stock_count.create`, `stock_count.read` | Yes |
| Balances, low stock, replenishment list, item ledger | existing `inventory.read` | Yes (already) |
| Opening stock, reversals, approving or rejecting adjustments | ADMIN and KITCHEN_MANAGER, checked by role on the server | Never |

- `stock_count.create` and `stock_count.read` are added to the
  KITCHEN_MANAGER set and the STAFF-assignable list. No other permission
  set changes. The permission rows are added by migration M2c; no grant
  is inserted, changed or deactivated.
- `inventory.create` and `inventory.update` gain no stock rights: counts
  use `stock_count.*`, and opening stock, reversals and approvals are
  role checks.
- **Known consequence, accepted with S1.** STAFF user #3 already holds
  active `consumption.create`, `consumption.read`, `consumption.update`
  and `inventory.read` grants (assigned by admin #1 on the staff
  permissions screen, 13–14 November 2026). From slice 4a user #3 sees
  balances and the item ledger; from slice 4b user #3 can record and
  confirm kitchen issues and unused returns. If that is not intended, an
  ADMIN revokes the codes on the staff permissions screen. This plan
  changes no grant.

### S2 — No negative balance by any path

Until Q9 is answered, every posting that lowers stock is refused if it
would take the item's balance on its campus below zero: issue
confirmation, approval of a negative adjustment, and reversal of an
opening entry or an unused return. The message names the item, the
balance and the shortfall. One shared check in the posting service, made
while the item rows are locked. If every movement has been recorded, a
count-based adjustment cannot go below zero, so a refusal points to a
missing record: the approver rejects the adjustment and the missing
receipt or a new count is entered.

### S3 — Opening stock

- ADMIN and KITCHEN_MANAGER only.
- At most one active opening entry per item per campus, with an effective
  date on or before today. It may be earlier than existing receipts.
- Corrected only by reversing it, with a reason, and entering a new one.

### S4 — Reversing a confirmed issue or unused return

- ADMIN and KITCHEN_MANAGER only; the whole document; reason required.
- Posts one `REVERSAL` movement per original movement, linked to it (each
  movement is reversed at most once); the document records who reversed
  it, when and why; audited in the same transaction.
- A return is reversed before the issue it came from: reversing an issue
  that still has a confirmed, unreversed return is refused.
- The corrected document is then entered again as a new document.
- Subject to S2 (reversing a return lowers stock). Line-level reversal is
  not built. Receipt movements are not reversed through this feature.

### S5 — Link between an issue and a meal

- Required: issue date, meal session and menu (the menu must belong to
  that meal session and campus). Remarks optional.
- "Responsible user" (STK02) is the signed-in user who records the issue;
  the confirming user is recorded separately. Cooks without accounts can
  be named in remarks.
- The link to a meal record is added in Stage 7. Until then STK02
  criterion 4 is partly met and **STK02 stays IN_PROGRESS**; it cannot
  become TESTED in Stage 4.

### S6 — Adjustment amount and timing, with blind counts

- **Blind counts.** The count entry screen shows items and units only,
  never the system balance. When the count is saved, the server records,
  for each line, the system balance at that moment, the physical quantity
  and the difference; they are never recalculated. Blind counting is a
  working procedure on the count screen, not an access control: a counter
  who also holds `inventory.read` can still open the balances screen.
- An adjustment is raised from a count line with a difference by an
  explicit action, never automatically. At most one PENDING adjustment
  per item per campus.
- **On approval** (ADMIN or KM who is not the counter, enforced by the
  API and by a database check) the difference measured at count time is
  posted, effective at the count time and created at approval. The
  approval screen shows the system balance at count time and now, and the
  movements since the count. Subject to S2.
- **On rejection** nothing is posted, the reason is kept, and a new count
  is needed.

### S7 — Migrations on the development database

Three additive migrations, one per slice (M2a, M2b, M2c; section 5). The
approval covers all three **only while each stays additive**: the single
change to existing rows is the backfill of the new ledger columns on the
existing `RECEIPT` movements in M2a. Anything else that would change or
delete existing data stops the work for a separate decision.

Each migration goes through these steps in order. If any step fails, the
work stops and is reported; nothing is applied.

1. Throwaway PostgreSQL 16 server on an isolated Docker network, removed
   afterwards: upgrade, downgrade and re-upgrade on an empty database and
   on a restored copy of the development data; existing tables keep their
   rows; models and migrated schema identical.
2. Full backend suite on `kitchen_copilot_test_db` with the one-off
   container command recorded in the Stage 3 evidence (no published ports,
   compose API not started).
3. Backup of `kitchen_copilot_db` with `pg_dump -Fc`, checked with
   `pg_restore --list`, kept outside the repository.
4. Read-only snapshot of the development database (row counts, write
   counters, STAFF grant fingerprints), then apply the one revision, then
   the snapshot again: only the expected tables and rows changed, grant
   fingerprints unchanged.
5. Read-only smoke test of the port 8000 API.

No Alembic or pytest run from the host against a real database; the
Homebrew PostgreSQL on port 5432 is not touched; the compose API stays
stopped; no Docker image is rebuilt without separate approval.

Receipt acceptance (`app/api/routes/receipts.py`, PUR03) must start
filling the new ledger columns in slice 4a, so the receipts tests
(SQLite and PostgreSQL) and the receipts browser checks are rerun then.

### Implementation choices that follow from the decisions

Approved 23 November 2026, with these conditions:

1. The historical check replays the item's movements in effective-time
   order and refuses a posting if the balance would be negative at any
   point. Movements with the same effective time are ordered
   deterministically: by posting order (movement id), with a new posting
   placed after the existing movements of its effective time. Backdated
   postings are tested.
2. A reversal is effective at its actual posting time; the original
   movement, with its own transaction date, is never changed.
3. One active opening entry per item per campus is enforced by the
   database. Reversing an opening keeps the opening, its movement and
   their audit rows.
4. Users with `stock_count.create`, ADMIN and KITCHEN_MANAGER may raise
   adjustment requests (slice 4c); only an independent eligible approver
   may approve them.

The choices:

- **S2 checks the running balance, not only today's.** Opening stock and
  adjustments can carry an earlier effective date, so the check refuses a
  posting if the running balance would go below zero at any point from
  its effective time to now.
- **Reversals are effective when posted.** The original stays unchanged
  at its own date; the reversal lowers or raises the balance from the
  reversal time on.
- **Opening entries are documents.** A `stock_openings` row (status
  ACTIVE or REVERSED) carries the database rule "one active opening per
  item per campus".
- **Who raises an adjustment.** Any user with `stock_count.create`, or an
  ADMIN or KM. Raising only requests; approval stays independent.

## 5. Design

### Migrations (S7; additive; no existing row changes in meaning)

- **M2a (slice 4a).** `stock_movements`: add `direction` (+1 or −1),
  `effective_at`, `source_key` (unique per campus) and `reversal_of_id`
  (unique: a movement is reversed at most once). Movement types
  `OPENING`, `RECEIPT`, `ISSUE`, `UNUSED_RETURN`, `ADJUSTMENT`,
  `REVERSAL` (`SUPPLIER_RETURN` reserved for PUR05, blocked by Q6). Index
  (campus, item, effective time). Backfill of the existing `RECEIPT` rows
  only: direction +1, effective time = the receipt's acceptance time,
  source key `RECEIPT_ITEM:<id>`. New `stock_openings` (item, entered
  quantity and unit, standard quantity, factor used, effective date,
  remarks, status ACTIVE / REVERSED, reversed by/at and reason) with a
  partial unique index: one ACTIVE opening per item per campus.
- **M2b (slice 4b).** `kitchen_issues` (issue date, meal session, menu,
  recorded by, remarks, status DRAFT / CONFIRMED / CANCELLED, confirmed
  by/at, reversed by/at and reason) and `kitchen_issue_items` (item,
  entered quantity and unit, standard quantity, factor used, remarks).
  `kitchen_returns` and `kitchen_return_items` (same status and reversal
  fields), each line linked to its issue line; returned never more than
  issued minus already returned. The meal-record link is added in
  Stage 7 (S5).
- **M2c (slice 4c).** `stock_counts` (counted at = when saved, counted
  by, reason, status) and `stock_count_items` (item, system balance when
  saved, physical quantity, difference — stored, never recalculated).
  `stock_adjustments` (one per count line with a difference; raised by,
  the counter copied from the count, status PENDING / APPROVED /
  REJECTED, decided by/at, reason) with a database check that the decider
  is not the counter and a partial unique index allowing one PENDING
  adjustment per item per campus. Permission module `stock_count` with
  `stock_count.create` and `stock_count.read` (permission rows only).

### Posting and concurrency (PostgreSQL)

All stock postings go through one service. Anything that lowers stock
(issue confirmation, negative adjustment, reversal of an opening entry or
a return) locks the affected item rows in id order, recalculates the
running balance, applies the S2 check and posts the movements with their
audit row in the same transaction. Unique `source_key` and
`reversal_of_id` stop double posting. Race tests: two issues for the last
stock; double confirmation; two approvers on one adjustment; a reversal
racing a return; two opening entries for one item.

### API (campus-scoped, permission-checked on the server)

- `GET /api/stock/balances` (filters: category, below minimum, search) and
  `GET /api/stock/replenishment` (items below minimum with the shortfall)
  — `inventory.read`.
- `GET /api/stock/items/{id}/ledger` (movements with running balance) —
  `inventory.read`.
- Opening stock: list, create, reverse — ADMIN and KM.
- Kitchen issues: list, create draft, edit draft, cancel draft, confirm —
  `consumption.*`; reverse — ADMIN and KM.
- Unused returns: create against a confirmed issue, confirm —
  `consumption.*`; reverse — ADMIN and KM.
- Counts: create (blind; the server records system balances when saved)
  — `stock_count.create`; list and detail — `stock_count.read`.
  Adjustments: raise from a count line — `stock_count.create`, ADMIN or
  KM; list pending — `stock_count.read`, ADMIN or KM; approve and reject —
  ADMIN and KM who did not count.

### Screens

Stock balances (low-stock filter, replenishment list, phone layout); item
ledger; opening stock (ADMIN/KM); kitchen issues (list, new, detail with
returns and net usage, Reverse with a reason for ADMIN/KM); stock counts
(blind entry, then detail with differences); adjustment approvals
(pending list with the balance at count time and now; the counter sees
"waiting for an independent approver"); the existing stock movement log
gains direction, effective date, source and reversal links. Navigation
and route guards follow S1; the staff permissions screen shows the new
`stock_count` module.

## 6. Order of work and estimate

Developer-days for one developer, each slice including its migration and
the S7 procedure, backend, screens, tests and documentation, reported
when finished. All decisions are approved; no slice is blocked.

| Slice | Scope | Requirements | Days |
|---|---|---|---|
| 4a — **built 23 Nov 2026; M2a applied to the development database** | M2a: ledger columns and receipt backfill; receipt acceptance fills the new columns; opening stock with reversal; balances, low stock, replenishment list; item ledger; movement log update | STK01, STK04 criteria 1–3 | 2.5–3 |
| 4b — **built 23 Nov 2026; M2b applied to the development database** | M2b: kitchen issues with the over-issue refusal; unused returns; net usage; reversals | STK02 (criterion 4 partly, S5), STK03, STK04 criterion 4, AT01 | 3–3.5 |
| 4c — **built 23 Nov 2026; M2c applied to the development database** | M2c: blind physical counts; adjustments with independent approval and no fallback; `stock_count` permissions | STK05, AT02 | 2.5–3 |
| — | Final verification: full PostgreSQL suite, port 8000 smoke test, browser suites, AT01 and AT02 walkthroughs | — | 1 |

Slice 4a status (23 November 2026): built and verified; migration
`b5e1d7c3a920` applied to `kitchen_copilot_db` after the S7 procedure;
evidence in `REQUIREMENTS-TRACEABILITY.md` section 2. STK01 and STK04
stay IN_PROGRESS until slices 4b and 4c.

Slice 4b status (23 November 2026): built and verified; migration
`c7d2e9f4a816` (M2b: kitchen issues and returns, append-only ledger
triggers) applied to `kitchen_copilot_db` after the S7 procedure; STK03
and AT01 TESTED, STK02 IN_PROGRESS (meal-record link, Stage 7); evidence
in `REQUIREMENTS-TRACEABILITY.md` section 2.

Slice 4c status (23 November 2026): built and verified; migration
`0e7d99065bd3` (M2c: stock counts, adjustments, `stock_count` permission
rows) applied to `kitchen_copilot_db` after the S7 procedure; section 10
records how it was built. Statuses and evidence are in
`REQUIREMENTS-TRACEABILITY.md` section 2.

Total about 9–10.5 days (previously estimated 12–15; receipts already
provide the ledger base, conversions and patterns). Q9 and Q10 do not
block building: the refusal and the no-fallback behaviour are what is
built until the client answers.

**Two-week target.** Stage 4 alone fills about two working weeks. Within
that window this stage delivers the approved stock essentials (AT01 and
AT02 runnable). Planning, meals, outsourced food, reports, administration
and the AI agent (`REMAINING-WORK.md` stages 5–12) do not fit in the same
two weeks; which of them comes next is your call.

## 7. Verification for TESTED

- One backend test per acceptance criterion (STK01–STK05), on SQLite and
  PostgreSQL, plus the race tests above; the full PostgreSQL suite.
- Decision tests: S1 permission matrix for ADMIN, KM, STAFF with and
  without each code, and another campus; S2 refusal on every path that
  lowers stock, including backdated postings; S3 second active opening
  and future date refused, reverse and re-enter works; S4 return reversed
  before its issue, each movement reversed once, STAFF refused; S6 count
  entry exposes no system balance, one pending adjustment per item, the
  counter refused by the API and by the database, rejection posts
  nothing.
- AT01 walkthrough: accept a receipt, issue, return unused; the receipt
  posts once, the issue lowers and the return restores stock, and the
  ledger balance equals the displayed balance.
- AT02 walkthrough: count differs; the system balance at count time is
  kept; stock is unchanged until approval; the counter cannot approve;
  another ADMIN/KM can.
- Browser checks for each screen as ADMIN, KITCHEN_MANAGER, STAFF with and
  without the assigned codes, another campus, and phone width.
- Migration evidence for M2a, M2b and M2c per the S7 procedure, with STAFF
  grant fingerprints unchanged across each apply.
- STK02 stays IN_PROGRESS until the meal-record link exists (S5).
  Nothing becomes ACCEPTED without the client.

## 8. Append-only ledger at database level — options (23 November 2026; options A and C approved the same day, see section 9)

Today the ledger is append-only in application code: no endpoint updates or
deletes a movement, and corrections are linked reversals. The database
itself still accepts an `UPDATE` or `DELETE` issued directly in SQL.

Facts that shape the options (read-only checks, 23 November 2026):
- The application connects as `kitchen`, which is a superuser, owns every
  table and is the only role that can log in.
- No triggers exist on any table.
- The only code that changed movement rows: the one-time M2a backfill, and
  one existing test that edits a movement's `created_at` to test the
  campus-local date filter (`tests/test_pur03_postgres.py`, line 153).

| Option | What it stops | What it does not stop | Risks and costs |
|---|---|---|---|
| **A. Trigger** refusing `UPDATE`, `DELETE` and `TRUNCATE` on `stock_movements` (a small additive migration; also attached to the test schema) | Accidental or ad-hoc edits and deletions from the app, scripts and SQL sessions, superuser included (triggers fire for superusers) | A superuser can disable the trigger (`ALTER TABLE … DISABLE TRIGGER`, `session_replication_role = replica`), drop the table or restore a backup | A future migration that must change existing movement rows has to disable and re-enable the trigger explicitly. The existing test above must be rewritten to insert its movement with the chosen time instead of editing it. Small runtime cost. Mistakes in the trigger's DDL would affect every posting, so it goes through the full S7 procedure |
| **B. Separate database roles**: a non-owner, non-superuser runtime role with `SELECT, INSERT` only on the ledger; migrations keep the owner role | Edits and deletions through the application's connection, including a compromised application | Anyone holding the owner or superuser credentials | New role and password; `DATABASE_URL` in `.env` changes (needs your approval); compose and deployment changes; grants for every table and default privileges for future tables; a misconfiguration stops the running API. Best done with release hardening (stage 13) |
| **C. ORM guard**: the application refuses to flush a changed or deleted `StockMovement` | Application code mistakes (a future endpoint or script using the ORM) | Raw SQL and anything outside the application | No migration; the same existing test needs the same rewrite |
| D. Tamper evidence: each movement stores a hash chained to the previous one for its item | Nothing; makes any later edit detectable by a verification run | — | Extra work in every posting (already under the item lock); a verification job; more complex reversals and backfills. Worth it only if auditors ask |
| E. Row-level security | — | The owner and superusers bypass it, and the application is both | No benefit with the current single role |

Recommendation: **A and C now**, in slice 4b's migration M2b (no separate
migration), with the one test rewritten; **B later** with deployment
hardening. Needs your explicit approval: yes (a trigger, a migration change
and an existing test change). Blocks slice 4b: no; if not approved, slice 4b
proceeds without it. `stock_openings` and the slice 4b documents stay
mutable by design (status changes), so only `stock_movements` would be
protected.

## 9. Slice 4b — kitchen issues and unused returns (prepared, approved and built 23 November 2026)

**Approved 23 November 2026:** 4b-1 to 4b-5 as recommended below.
- 4b-1: an issue dated today takes effect at its confirmation time; a
  backdated issue at the end of its issue date (23:59:59.999999 campus time).
- 4b-2: returns follow the same rule and never take effect before their
  issue.
- 4b-3: users with `consumption.update` may confirm their own drafts.
- 4b-4: KI-00001 and KR-00001, numbered per campus in sequence.
- 4b-5: both the database trigger (refusing `UPDATE`, `DELETE` and
  `TRUNCATE` on `stock_movements`) and the application guard (option A and
  C, section 8), in migration M2b.

With these requirements: the ledger stays append-only and corrections are
reversals; the existing test that edits a movement's `created_at` is
rewritten without weakening the protection; the form-options endpoint lets
STAFF with the approved `consumption.*` codes use the forms without
`menu.read` or `inventory.read`; no STAFF grant or permission changes; the
duplicate campus 1 meal sessions are documented, not merged, renamed or
deleted; slice 4c is not started; M2b follows the S7 procedure with a
verified backup.

Scope: STK02 (criterion 4 partly, S5), STK03, STK04 criterion 4, AT01.
Estimate 3–3.5 days. Everything below follows the approved decisions
S1, S2, S4 and S5 and the interim Q9 behaviour; points needing your
approval are listed at the end.

### Migration M2b (additive; four new tables, no backfill, no permission rows)

- `kitchen_issues`: campus, `issue_seq` and `issue_number` (KI-00001, unique
  per campus), `issue_date` (today or earlier), `meal_session_id`, `menu_id`
  (the menu must belong to the session), `remarks`, `status` DRAFT /
  CONFIRMED / CANCELLED / REVERSED, `effective_at` (set on confirmation),
  created by/at, updated at, confirmed by/at, cancelled by/at and reason,
  reversed by/at and reason. Checks: each status has exactly its own fields.
- `kitchen_issue_items`: issue, item, entered quantity and unit, conversion
  factor used, standard quantity and unit, remarks; one line per item per
  issue; quantities above zero.
- `kitchen_returns`: campus, `return_number` (KR-00001), `issue_id`,
  `return_date` (not before the issue date), same status and audit fields as
  issues.
- `kitchen_return_items`: return, `issue_item_id`, entered quantity and unit,
  factor, standard quantity, remarks; one line per issue line per return.
- No change to `stock_movements`: ISSUE (−1) and UNUSED_RETURN (+1) are
  already allowed. Source keys `ISSUE_ITEM:<line>` and `RETURN_ITEM:<line>`;
  reference types `KITCHEN_ISSUE` and `KITCHEN_RETURN`.
- If option A or C in section 8 is approved, it is added here.

### Posting rules

- Drafts post nothing and may be saved even when stock is short (Q9
  interim). Confirmation posts one ISSUE movement per line through the
  shared posting service: item rows locked in id order, the history check
  of S2, refusal with the shortfall named.
- A return line may not exceed the issue line's quantity minus what
  confirmed, unreversed returns already gave back (checked under a lock on
  the issue). Confirmation posts UNUSED_RETURN movements.
- Net usage per line = issued − returned (standard unit), shown with both
  figures separately (STK03).
- Reversal (ADMIN and KITCHEN_MANAGER, reason required, S4): a whole issue
  or return. An issue with a confirmed, unreversed return is refused until
  the return is reversed. Reversing a return lowers stock, so it goes
  through the S2 check. Effective at the posting time; originals unchanged.
- Confirmed documents are never edited; a correction is reversal and
  re-entry.

### API (campus-scoped, permission-checked on the server)

- Kitchen issues: list (date range, session, menu, status, item), create
  draft, detail (lines, returns, net usage), edit draft, cancel draft with a
  reason, confirm — `consumption.read`, `.create`, `.update` (S1); reverse —
  ADMIN and KITCHEN_MANAGER.
- Unused returns: create draft against a confirmed issue, edit, cancel,
  confirm — `consumption.*`; reverse — ADMIN and KITCHEN_MANAGER.
- An options endpoint for the entry forms (active meal sessions, menus,
  items, units and conversions) guarded by `consumption.create`. Without it
  a STAFF user holding only `consumption.*` could not fill the form: the
  master-data lists need `menu.read` and `inventory.read`.
- Available stock is shown on the form only to users holding
  `inventory.read`; the refusal message on confirmation names the shortfall
  (S2) for everyone who may confirm.

### Screens

Kitchen issues under Operations: list with status tabs and filters; new
issue (date, session, menu, item lines with unit conversion); issue detail
(issued, returned and net per line; returns; Edit, Cancel and Confirm for
drafts; Record return; Reverse for ADMIN and KITCHEN_MANAGER); return form
listing what each line can still return. The movement log, item ledger and
balances already show ISSUE, UNUSED_RETURN and REVERSAL rows.

### Tests and verification

One test per STK02, STK03 and STK04 criterion 4; the S4 rules; races on
PostgreSQL (two confirmations for the last stock, double confirmation, two
returns exceeding the issue line, a return racing the issue's reversal); the
AT01 walkthrough (receipt, issue, return, reversal; ledger balance equals
the displayed balance) as a backend test and in the browser; browser checks
as ADMIN, KITCHEN_MANAGER, STAFF with and without `consumption.*`, another
campus and phone width; M2b through the S7 procedure.

Known consequence (accepted with S1): STAFF user #3 holds
`consumption.create`, `.read` and `.update`, so from slice 4b they can record
and confirm kitchen issues and returns.

### Points needing your approval before slice 4b starts

| # | Question | Recommendation |
|---|---|---|
| 4b-1 | When is an issue effective (the time the history check and the ledger use)? Meal sessions have no times. | Dated today: the confirmation time. Dated earlier (entered late): 23:59:59 campus time on the issue date, so that day's receipts count and the history check judges the real day. |
| 4b-2 | When is an unused return effective? | The same rule on the return date, never before its issue's effective time. |
| 4b-3 | May the person who recorded a draft also confirm it? | Yes. S1 gives confirmation to `consumption.update`, and the proposal has no second-person step for issues. |
| 4b-4 | Document numbers | KI-00001 and KR-00001 per campus, like purchase orders. |
| 4b-5 | Section 8 protection | Option A and C in M2b, or neither. |

Also for your attention (not blocking): campus 1 has both "Breakfast" and
"breakfast" as active meal sessions, plus "early morning". Issues will link
to whichever is chosen. Cleaning this up is the master-data gap C5 / Q2
(`REMAINING-WORK.md` stage 5), not part of slice 4b.

## 10. Slice 4c — physical counts and adjustments (built 23 November 2026)

Authorised 23 November 2026, with these requirements: the counter never
approves; the count screen stays blind; movements between the count and the
approval are handled without overwriting the ledger or producing a wrong
balance; a rejection posts nothing; every approval is an append-only movement
with an audit row; S2 applies across the whole history; no STAFF grant or
other role permission changes and nothing is granted automatically; the
append-only triggers and application guard stay; the duplicate meal sessions
stay as they are; the missing draft-return editing screen is assessed
separately, not added to this slice. Scope: STK05, AT02.

### What was built, against the decisions

- **S1.** Module `stock_count` with `stock_count.create` (record a count,
  raise an adjustment request) and `stock_count.read` (view counts and
  adjustments): permission rows added by M2c, both codes added to the
  KITCHEN_MANAGER set and to the STAFF-assignable list, exactly as S1 states.
  No grant was inserted; no other code moved in or out of any set. Approving
  and rejecting are role checks (ADMIN, KITCHEN_MANAGER).
- **S6, blind counts.** The count form's options carry items, categories,
  units and conversions only, never a balance, whatever other codes the
  user holds. The count API refuses any extra field, so a client cannot
  send a system balance or difference. When a count is saved the server
  locks the counted items, takes the count time and records, per line, the
  system balance at that moment, the physical quantity (as entered and in
  the standard unit, with the factor used) and the difference. A counter
  who holds `stock_count.create` but not `.read` gets only the count number
  back. Blind counting is a procedure on the count screen; a counter who
  also holds `inventory.read` can still open the balances screen (as
  approved).
- **S6, adjustments.** Raised from one count line by an explicit action with
  a reason (`stock_count.create`, ADMIN or KITCHEN_MANAGER, implementation
  choice 4); one per count line; at most one PENDING per item per campus (a
  partial unique index). Approved or rejected only by an ADMIN or
  KITCHEN_MANAGER who did not perform the count: refused by the API (403)
  and by the database (`decided_by <> counted_by`). The counter on the
  adjustment is copied from the count through a composite foreign key, so
  it cannot differ from the real counter. Approval posts the difference
  measured at count time as one ADJUSTMENT movement (source
  `ADJUSTMENT:<id>`), effective at the count time and created at approval;
  rejection keeps the reason and posts nothing; the line cannot raise again
  (a new count is needed).
- **S2.** A negative adjustment goes through the shared posting check: it is
  refused if the balance would go below zero at any point from the count
  time onwards, and the message tells the approver to reject it and record
  the missing movement or count again.
- **Q10, interim.** No fallback approver. The adjustment stays PENDING; the
  screen says why, including when no other active ADMIN or KITCHEN_MANAGER
  exists on the campus.

### Movements between the count and the approval

The stored difference reconciles the ledger to the counted quantity only if
the ledger at the count time is still what the counter was compared
against. So:
- a movement **effective after** the count time (an issue, receipt or
  return recorded after the count) is kept unchanged and follows the
  adjustment in ledger order: after approval the ledger holds the counted
  quantity at the count time and today's balance is that quantity plus
  everything since;
- a movement **effective at or before** the count time but posted after the
  count was saved (a late kitchen issue, an opening entry, another count's
  adjustment, or a posting that raced the count) changes the ledger at the
  count time. Raising and approving are then refused with an explanation,
  and the approver rejects the adjustment and the item is counted again.
  The approval screen shows the balance at the count time then and now,
  today's balance, the balance after approval and every movement posted
  since the count, flagging those dated before it.
The same rule stops one difference being applied twice (two counts of one
item, or a count saved while another count's adjustment was pending). No
movement is ever edited.

### Choices made while building (within the decisions; for your review)

| Choice | Why |
|---|---|
| Counts are numbered SC-00001 per campus, like KI and KR (4b-4) | A visible reference for the ledger and lists |
| No status column on `stock_counts` (section 5 listed one) | A saved count never changes (STK05 criterion 3); its state is shown from its lines' adjustments |
| A count is saved in one step; there is no draft count | The count time and system balances are taken at saving; a draft would need its own rules |
| Zero is a valid count (nothing found); a blank line is "not counted" | Needed to record that an item is missing |
| Approval and rejection need the same independence; the counter cannot withdraw a request | Section 5: "approve and reject — ADMIN and KM who did not count" |
| The approver may add an optional note; a rejection needs a reason | S6: "the reason is kept" |
| Saved counts are also protected by the application guard (no ORM update or delete) | STK05 criterion 3. A database trigger for counts was not added: it would be a new trigger needing its own approval |
| A STAFF user with `stock_count.create` but not `.read` sees a "Record Stock Count" menu entry | Without it the menu would offer no way to the count screen; it opens nothing the route guard does not already allow |
| Current balances and movements since the count are shown to users holding `inventory.read` only | Same rule as the kitchen forms (slice 4b); the stored count figures are visible with `stock_count.read` |

### Found during verification: a deadlock, fixed

The PostgreSQL race tests failed intermittently (3 of 7 runs): a count saved
while an issue for the same item was being confirmed. Document numbering
locked the campus row `FOR UPDATE`; a posting that already held an item lock
then waited for that campus row (its insert's foreign key takes `FOR KEY
SHARE`), while the numbering transaction waited for the item. PostgreSQL
aborted one of them, so the user saw a server error and nothing was saved.
The same cycle existed since slice 4b between saving a draft kitchen issue
and confirming another issue for the same item. Fix: the numbering lock is
now `FOR NO KEY UPDATE`, which still serialises numbering but no longer
blocks foreign-key checks (one line in `next_number`, shared by KI, KR and
SC numbering). Regression tests: a deterministic lock check, and eight
rounds of a count, a confirmation and a new draft for one item at once;
both fail against the old lock and pass with the new one. No data was ever
affected: an aborted transaction writes nothing.

### Migration M2c (`0e7d99065bd3`, additive)

Three new tables (`stock_counts`, `stock_count_items`, `stock_adjustments`)
and the `stock_count` module with its two permission rows. No existing
table, column or row changes; `stock_movements` and its append-only triggers
are not touched (ADJUSTMENT was already an allowed type). The downgrade
refuses while counts, adjustment movements or `stock_count` grants exist.

### Not in this slice

- Editing a draft unused return on screen (slice 4b gap): assessed
  separately below; not built.
- Database-level protection for saved counts (a trigger): needs approval.
- Separate database roles (section 8, option B): deployment hardening.

### Assessment: editing a draft unused return on screen

The API already supports it (`PUT /api/kitchen-returns/{id}`, slice 4b,
tested). The screen offers Confirm and Cancel for a draft return, so a wrong
draft is cancelled with a reason and recorded again. No approved acceptance
criterion requires on-screen editing: STK03 asks that confirmed returns add
stock, issued and returned stay separate, net usage is shown and each return
references its issue, all met. Section 9's screens list "Edit, Cancel and
Confirm for drafts" next to the issue actions, which can be read as covering
draft returns too. Recommendation: add an Edit action on the draft return
(reusing the return form, about half a day) when you choose; it changes no
rule and no data. Not built in slice 4c.

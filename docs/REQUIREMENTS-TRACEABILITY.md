
# Kitchen Copilot — Requirements Traceability

Source: Campus Software Requirements Document (SRD) v1.0

Status: Week 1 implementation tracking — requirement-level progress recorded from verified implementation and test evidence.

## 1. Purchase and Supplier Management

| ID | Requirement | Status |
|---|---|---|
| PUR01 | Record Purchases and Bill Attachments | TESTED |
| PUR02 | Calculate Bill Totals | TESTED |
| PUR03 | Record Accepted Receipts | IN_PROGRESS |
| PUR04 | Track Supplier Payments and Balances | TESTED |
| PUR05 | Record Supplier Returns and Credits | PENDING |

Titles match the approved proposal (`PROPOSAL.md` §5.1, PUR01–PUR05),
corrected 18 November 2026. Only the wording changed; statuses are set
from evidence alone. PUR05 is on hold until client question Q6 (how
supplier credits affect what is owed) is answered.

### Evidence (18 November 2026)

TESTED means the automated verification below passed. None of these is
ACCEPTED: that needs the client's confirmation.

**PUR02 — Calculate Bill Totals: TESTED.** One explicit test per proposal
criterion (`services/api/tests/test_pur02_bill_totals.py`, in-memory SQLite):
1. Item total = quantity × unit rate: `test_criterion_1_item_total_is_quantity_times_unit_rate`.
2. Discount and additional charges recorded separately: `test_criterion_2_discount_and_charges_are_recorded_separately`.
3. Bill total includes them consistently: `test_criterion_3_bill_total_includes_discount_and_charges`.
4. Purchase rates remain available, unchanged: `test_criterion_4_purchase_rates_stay_available_unchanged`.
5. Exact decimal arithmetic: `test_criterion_5_totals_use_exact_decimal_arithmetic`,
   and on PostgreSQL `test_pur02_bill_totals_are_exact_at_scale_on_postgres`
   (exact NUMERIC storage near the column limits).
The bill-entry screen uses the same rules (`apps/web/tests/billMath.test.mjs`).

**PUR04 — Track Supplier Payments and Balances: TESTED.** All five proposal
criteria (payments linked to bills; date and amount; balances recalculated;
supplier-wise summaries; purchase expenditure and supplier payments reported
separately) and the §5.8 export and print requirements for this report are
verified by:
- backend tests on in-memory SQLite and on the Docker PostgreSQL test
  database (full suite 343 passed, twice), including concurrent payments,
  campus isolation and every role;
- frontend unit tests;
- headless-browser checks of the payment, balance, bill and report screens,
  the Excel and PDF exports, and the print view, with the downloaded files'
  contents compared with the screen.

**AT08 — Supplier payment reconciliation and exports: TESTED** by the same
automated checks: full and partial payments reconcile with bill balances;
outstanding supplier amounts are correct; exported totals equal the
on-screen totals for the same filters; Excel and PDF files keep the period,
supplier filter and totals. A client walkthrough is still needed for
ACCEPTED.

**Not included:** supplier-return credits (PUR05), on hold until client
question Q6 is answered.

**PUR01 — Record Purchases and Bill Attachments: TESTED.** Built
18 November 2026 to the decisions approved that day (attachments: PDF,
JPEG, PNG or WEBP recognised from content, 10 MB each, 10 per bill,
permanent, upload with `purchase_order.create`, view with
`purchase_order.read`; duplicates: exact invoice numbers refused, numbers
equal apart from case, spaces and punctuation flagged, cleared by a user
with `purchase_order.update` with a note). Evidence, all on the final code:
- **PostgreSQL** (throwaway PostgreSQL 16 server on an isolated Docker
  network, removed afterwards; the development database was not touched):
  migration `e7b3c5a19d42` upgraded, downgraded to `d4e8a91b2c70` and
  upgraded again on an empty database and on a restored copy of the
  development data (all 25 existing tables kept their 599 rows; models
  and migrated schema identical); `services/api/tests/test_pur01_postgres.py`
  7 of 7, its two concurrency tests a further 5 runs each; full backend
  suite 393 of 393.
- **In-memory SQLite:** 43 of 43 tests in
  `services/api/tests/test_pur01_purchase_records.py`.
- **Headless browser** against a SQLite-backed scratch API: 35 of 35
  checks (ADMIN, KITCHEN_MANAGER, STAFF with and without a read grant,
  another campus, 390 px phone width); the earlier browser suites still
  pass (payments 64, bills and report 62, exports 26, export file
  contents 25).
1. All required fields recorded: `test_criterion_1_every_required_field_is_recorded`.
2. Multiple item lines: `test_criterion_2_a_bill_holds_multiple_lines`.
3. Bill images and documents attach: upload, list, download and view
   tests per file type, refusal by content (415), size (413), empty
   file (422), undeclared upload size (411), ten-file limit, same file
   once, permissions, campus isolation, CSRF, audit, no file left behind
   by a failed save and none removed after a successful one
   (`services/api/tests/test_pur01_purchase_records.py`), plus browser checks.
4. Possible duplicates flagged for review: flagging, the pre-save check,
   the review list and the audited review, including Malayalam and
   full-width digits (same file), plus browser checks.
5. Original details preserved: `test_criterion_5_original_details_are_preserved`
   (bill unchanged after attachments and review; PUT, PATCH and DELETE
   refused).

Migration `e7b3c5a19d42` was applied to the Docker development database
on 18 November 2026 after a verified backup (schema checked; PUR01 tests
50 of 50 on PostgreSQL; read-only API smoke test 11 of 11). Still open
(not acceptance criteria): the production storage backend (decision D9)
and a persistent attachment folder for the Docker API. ACCEPTED needs the
client's confirmation.

**PUR03 — Record Accepted Receipts: IN_PROGRESS.** Receipt screens and
API completed 18 November 2026 (list, new receipt from a bill, draft
correction and cancellation with a reason, acceptance, stock movement log,
receiving progress in the bill detail). Permissions are the existing codes:
`inventory.read` to view, `inventory.create` to record a draft,
`inventory.update` to correct, cancel or accept. Evidence, all on the
final code:
- **PostgreSQL** (`kitchen_copilot_test_db`): `test_pur03_postgres.py`
  4 of 4 (simultaneous drafts never exceed the billed quantity, a receipt
  accepted from several sessions posts stock once, accept and cancel racing
  leave exactly one outcome, campus-local days in the stock log); the three
  race tests a further 3 runs each; with `test_pur03_receipts.py` and the
  existing `test_receipts.py`, 30 of 30.
- **In-memory SQLite:** `test_pur03_receipts.py` 18 of 18.
- **Frontend unit tests:** `apps/web/tests/receiptMath.test.mjs` (exact
  quantities, entry validation, rejected = received − accepted).
- **Headless browser** against a SQLite-backed scratch API: 57 of 57
  checks (ADMIN, KITCHEN_MANAGER, STAFF with and without `inventory.read`,
  another campus, 390 px phone width).

By criterion:
1. Linked to its source purchase — met: every receipt belongs to a bill;
   list, detail and stock log show the bill and supplier
   (`test_criterion_1_receipts_are_linked_to_their_bill`).
2. Ordered, billed and accepted quantities distinguishable — met for
   bills entered against a purchase order (Stage 3, 20 November 2026):
   ordered (from the order line, converted into the bill line's unit),
   billed, received, accepted, rejected, held in drafts and left to receive
   are kept and shown separately on the bill, the receipt entry and the
   order (`test_criterion_2_billed_received_accepted_and_rejected_are_separate`;
   `test_bills_link_to_order_lines_and_progress_is_in_the_order_unit`;
   browser: ordered 60 kg, billed 62 kg, received 62 kg, accepted 60 kg,
   rejected 2 kg). A bill entered without an order has no ordered
   quantity; none is invented.
3. Only confirmed accepted quantities increase stock — met
   (`test_criterion_3_only_accepted_quantity_reaches_stock`; browser: 30 kg
   of 32 kg received posted, 2 kg rejected not; grams converted to kg).
4. Duplicate posting prevented — met
   (`test_criterion_4_a_receipt_posts_stock_once`; PostgreSQL race test).
5. Drafts do not affect stock — met
   (`test_criterion_5_drafts_never_touch_stock`).

Assumption awaiting client confirmation (`CLIENT-QUESTIONS.md` §4.3, "Can
a purchase have multiple receipts?"): several partial receipts per bill
are allowed, together never more than the billed quantity. Cancelling a
draft and correcting a draft before acceptance are implementation choices
(audited, never affecting stock), not client-confirmed rules.

Remaining before PUR03 can be TESTED: the client's answer on multiple
receipts per purchase. The full PostgreSQL regression on the final Stage 3
code passed on 20 November 2026 (453 of 453, see Stage 3 below).

**Stage 3 — Purchase orders and supplier-bill permissions: TESTED
(20 November 2026).** Not ACCEPTED: that needs the client. Open client
questions are unchanged (who approves purchases; amending placed orders;
whether over-billing is acceptable). Decisions of 18 November 2026:
`purchase_order.*` now guards genuine purchase orders and the new
`purchase_bill.*` guards supplier bills, payments, balances, the
purchases-versus-payments report and attachments; ADMIN and
KITCHEN_MANAGER hold both; neither namespace is assignable to STAFF; older
STAFF grants of `purchase_order.*` were copied to `purchase_bill.*` and
kept; no approval step; only drafts are edited; bills may exceed the
ordered quantity and the excess is shown.

**Correction of 20 November 2026 — STAFF have no purchase-order access.**
The kept `purchase_order.*` rows (STAFF user #3 in the development
database holds create, read and update) had given that user purchase-order
authority. The API now refuses every purchase-order permission to STAFF
before any assignment is consulted (`STAFF_EXCLUDED_PERMISSIONS` in
`app/api/dependencies.py`); entering a bill against an order and the
order picker in bill entry also need order access. The rows are not
changed or deleted: they are kept as history, reported as "no effect" on
the staff page and left out of the user's effective permissions. Bill
access through the `purchase_bill.*` copies is unchanged. Evidence:
`test_staff_never_reach_purchase_orders_even_with_older_grants` (all eight
order operations 403 with user #3's exact grants; rows unchanged; bills
without an order still 201, against an order 403),
`test_admin_and_kitchen_manager_perform_every_order_operation`,
`test_staff_detail_marks_kept_order_grants_as_not_effective`; browser:
a STAFF user with an older `purchase_order.read` grant sees no Purchase
Orders, is sent back from the page and gets 403 from the API.

Also decided on 20 November 2026: user #3's three `purchase_order.*` rows
stay unchanged (not deactivated) for historical traceability; the API
restriction above is the security control. Purchase-order information is
not shown through bill or inventory permissions either: for users without
order access (all STAFF) the bill detail and list, the bill's receiving
view and the dashboard activity feed carry no order id, order number,
order-line link or ordered quantity, and the screens show none
(`test_order_information_is_hidden_from_staff`; browser: a STAFF user
with bill and inventory access sees the bill and its receiving progress
without any order reference).

Evidence:
- **Migration `a3c9e1f47b20`** (throwaway PostgreSQL server, removed
  afterwards): upgrade, downgrade and re-upgrade on an empty database and
  on a restored copy of the development data (grants copied with the
  active flag and assigning admin, originals untouched, one audit row per
  copy, nothing else changed; models and schema identical). Applied to the
  Docker development database on 18 November 2026 after a verified backup.
- **PostgreSQL** (`kitchen_copilot_test_db`, 18 November 2026): order and
  permission-affected suites 181 of 181, including simultaneous order
  numbering and a cancellation racing a bill entry.
- **In-memory SQLite** (20 November 2026, final code): 29 of 29 in
  `services/api/tests/test_purchase_orders.py`; 212 of 212 across the
  purchasing and permission suites.
- **Frontend:** unit tests 37 of 37 (`orderForm.test.mjs` included);
  TypeScript, ESLint and the production build pass.
- **Headless browser** against a SQLite-backed scratch API: 42 of 42
  purchase-order checks (create with validation, edit, place, bill against
  the order with over-billing flagged, receipt showing ordered quantities,
  close, cancel, list, KITCHEN_MANAGER, STAFF with an older
  `purchase_order.read` grant refused, STAFF with only `purchase_bill.read`,
  no order information for a STAFF user with bill and inventory access,
  another campus, 390 px);
  the earlier suites still pass on the final code after the permission
  split (payments 64, bills and report 62, exports 26, export file
  contents 25, PUR01 35, PUR03 57).
- **Full backend suite on PostgreSQL** (20 November 2026, final code,
  `kitchen_copilot_test_db` on the Docker `db` server, existing `api`
  image, no rebuild): three full runs, each 453 passed, 0 failed,
  0 skipped, 0 errors, in 24 files, among them `test_purchase_orders.py`
  29, `test_purchase_orders_postgres.py` 5, `test_pur03_receipts.py` 18,
  `test_pur03_postgres.py` 4 and `test_pur04_postgres.py` 19. The four
  PostgreSQL-only files (35 tests, including all 12 concurrency tests)
  were repeated five more times: 35 of 35 each time, no flaky result.
  One warning per run, from a test that signs a reset link with a
  deliberately short foreign key. Command:
  `docker compose run --rm --no-deps -T -e PYTHONDONTWRITEBYTECODE=1
  -e ATTACHMENT_STORAGE_DIR=/tmp/kc-attachments
  -v "$PWD/services/api:/app/services/api:ro" api python -m pytest
  -p no:cacheprovider tests -q -rfEs`. The test configuration always
  replaces the database name with `kitchen_copilot_test_db` and overrides
  every request session; the development database recorded no inserted,
  updated or deleted rows during any run.
- **Development API smoke test** (20 November 2026, the developer's port
  8000 API on the Docker development database `kitchen_copilot_db`,
  revision `a3c9e1f47b20`; GET requests and one refused login only):
  54 of 54 (after correcting one over-strict check of the test script
  itself, which counted the field name `purchase_order_number` — always
  `null` for STAFF — as order data). Connected to port 5433, not the
  Homebrew server; orders, bills, attachments, duplicate review,
  receiving, receipts, stock log, payments, balances, report, staff
  permissions and dashboard for ADMIN; orders, billable orders, bills,
  receiving, receipts, payments, balances and dashboard for
  KITCHEN_MANAGER (staff permission screens refused); neither namespace
  assignable to STAFF; user #3's kept order grants shown as not
  effective; user #3 refused all three order reads (403), and given every
  bill, payment, balance, report, receipt, receiving, stock-log and
  dashboard read their grants allow, none carrying an order id, order
  number, order-line link, ordered quantity or purchase-order activity.
  The development database has no orders yet, so the order-linked cases
  rest on the suites above.
- **User #3's grants** (read-only, 20 November 2026): 23 rows, all
  active. #4–23 assigned by admin #1 on the staff permissions screen on
  13 November 2026 (audit #21 and #26; most revoked the same day and
  reactivated on 14 November), including the kept `purchase_order.*` rows
  #11–13; #24–26 are their `purchase_bill.*` copies made by migration
  `a3c9e1f47b20`. Identical before and after the verification, as were
  every STAFF grant, the revision and every table's row count.

**Reports — Export and print support: TESTED (26 November 2026).** Every
§5.8 report has Excel, PDF and a print view on the Reports screen (Stage 9;
evidence in §6); the purchases-versus-payments and outsourced reports keep
their own screens. Not ACCEPTED.

## 2. Stock and Inventory Management

| ID | Requirement | Status |
|---|---|---|
| STK01 | Opening stock and stock ledger | IN_PROGRESS |
| STK02 | Kitchen stock issues | TESTED |
| STK03 | Unused stock returns | TESTED |
| STK04 | Stock balances and low-stock monitoring | TESTED |
| STK05 | Physical stock counts and adjustments | TESTED |

### Stage 4 slice 4a — stock ledger, opening stock, balances (23 November 2026)

Built to the decisions of 23 November 2026 (`STAGE-4-STOCK-PLAN.md`
section 4, S1–S7 and the four approved implementation choices). Neither
requirement is TESTED yet: the rest of STK01 and STK04 comes with slices
4b and 4c. Nothing here is ACCEPTED.

**STK01 — Opening stock and stock ledger: IN_PROGRESS.**
1. Authorized users record opening stock with an effective date: ADMIN and
   KITCHEN_MANAGER only, by role (S3); never STAFF, whatever codes a STAFF
   user holds. Date today or earlier; one active entry per item per campus,
   enforced by a partial unique index; corrected only by reversal with a
   reason and re-entry. Met.
2. Opening stock creates a separate OPENING movement (source key
   `OPENING:<entry>`), effective at 00:00 campus time on its date. Met.
3. The ledger records receipts, kitchen issues, unused returns, supplier
   returns, approved adjustments and reversals: receipts, opening stock
   and reversals are posted now; the schema accepts every type. Kitchen
   issues and unused returns come in slice 4b, adjustments in 4c, supplier
   returns with PUR05 (on hold for Q6). Partly met.
4. Every movement carries its type, quantity, direction, effective time,
   posting time and source reference (migration `b5e1d7c3a920`). Met.
5. Posted movements are not directly edited or deleted: no endpoint
   changes or deletes a movement; corrections are linked REVERSAL rows
   (each movement reversed at most once, enforced by the database), and
   database checks fix each type's direction and the reversal link. A user
   with direct SQL access could still change rows: no database trigger
   forbids it (not in the approved plan). Met at the application level.

**STK04 — Stock balances and low-stock monitoring: IN_PROGRESS** (was
PENDING).
1. Balances are calculated from posted movements only
   (sum of direction × quantity, in the item's standard unit). Met.
2. Items below their configured minimum are identified (minimum above
   zero and balance below it; an item with no minimum is never flagged).
   Met.
3. A replenishment list is available: active items below minimum with the
   quantity needed to reach it, by category. Met.
4. Issues exceeding available stock are prevented: comes with kitchen
   issues in slice 4b. The shared posting check it will use is built and
   tested now (S2).

**S2 — no balance below zero, at any point in the history.** Every posting
that lowers stock locks the item rows in id order and replays the item's
movements in effective-time order, then posting order, with a new posting
placed after existing movements of the same effective time; it is refused
if the balance would be negative at any point from the new posting onwards
(tests: backdated outflow refused when an earlier point goes negative
although today's balance would be positive; accepted when every point stays
at or above zero; same-time ordering both ways; postings in one call
replayed in order; each item on its own history; reversal of an opening
refused when later stock left the store).

Evidence:
- **Migration `b5e1d7c3a920` (M2a)** on a throwaway PostgreSQL 16 server
  (internal Docker network, no published ports, no route to the
  development database; removed afterwards): empty database 11 of 11
  checks; restored copy of the development data 21 of 21 — the upgrade is
  refused while any non-receipt movement exists; the 6 receipt movements
  are backfilled and keep their original values; every other table keeps
  its rows; the partial unique index and the check constraints hold; the
  downgrade is refused while opening stock exists; downgrade and
  re-upgrade; models and migrated schema identical. The slice-4a API on
  that copy: 11 of 11 (balances from the backfilled receipts, ledger,
  opening entry and reversal, STAFF #3 refused opening stock, campus
  isolation).
- **Applied to the Docker development database** (`kitchen_copilot_db`)
  on 23 November 2026, `a3c9e1f47b20` → `b5e1d7c3a920`, from a one-off
  container, after a verified backup
  (`~/kitchen-copilot-backups/pre-b5e1d7c3a920-20261123-110618`,
  `pg_dump -Fc`, read back in full, 30 table-data entries). The only rows
  written in application tables were the 6 approved receipt movements
  (direction +1, effective time = the receipt's acceptance time, source
  `RECEIPT_ITEM:<receipt line>`) and the revision row. Every table's row
  count, the original movement columns, user #3's 23 grants and all 26
  STAFF grants were identical before and after.
- **Backend tests:** `test_stock_ledger.py` 54 (in-memory SQLite) and
  `test_stock_ledger_postgres.py` 7 (simultaneous openings, simultaneous
  reversals, racing outflows under the item lock, the backdated check, the
  partial unique index and check constraints, campus-midnight effective
  times). Full suite on PostgreSQL (`kitchen_copilot_test_db`, slice-4a
  code mounted read-only, the Stage 3 command): two runs, 514 passed each
  (453 earlier + 61 new), 0 failed, 0 skipped, 0 errors; the
  PostgreSQL-only files (42 tests, stock and earlier) five more times,
  42 of 42 each.
- **Frontend:** unit tests 46 of 46 (9 new for the stock display and
  opening-entry rules); TypeScript, ESLint and the production build pass.
- **Headless browser** against a SQLite-backed scratch API: 55 of 55, no
  page errors — balances, below-minimum and search filters, replenishment
  list, item ledger, opening stock with unit conversion, form validation,
  reversal with a reason, re-entry after reversal, movement log;
  KITCHEN_MANAGER; a STAFF user holding `inventory.*` and `consumption.*` (like
  user #3) sees balances but no opening stock and is refused by the API;
  a STAFF user without `inventory.read`; another campus; 390 px phone
  width on every new screen and the opening form.
- **Development API smoke test** (port 8000, read-only, after the apply):
  stock 23 of 23 (balances equal the ledger sums on both campuses,
  replenishment list, Rice ledger effective at its receipt's acceptance,
  opening stock list empty, STAFF #3 refused opening stock, movement log
  and dashboard carry direction); the Stage 3 suite 54 of 54. No row was
  written during the smoke tests.
- **Two short code/database mismatches on 23 November 2026** (about a
  minute and a half before the migration, about a minute after it), both
  on the port 8000 API, both without data impact; causes and corrections
  in `DEVELOPMENT-SAFETY.md` section 6.1.
- **Generated API types** (`apps/web/src/types/api.ts`) regenerated on
  23 November 2026 from the running slice-4a API (66 paths), identical to
  the output from a schema exported offline from the working tree.

### Stage 4 slice 4b — kitchen issues, unused returns, append-only ledger (23 November 2026)

Built to decisions S1, S2, S4, S5 and 4b-1 to 4b-5 (`STAGE-4-STOCK-PLAN.md`
sections 4 and 9). Nothing here is ACCEPTED. STK01 and STK04 stay
IN_PROGRESS until all Stage 4 slices are complete (your instruction of
23 November 2026), although STK04 criterion 4 is now met.

**STK02 — Kitchen stock issues: IN_PROGRESS** (was PENDING).
1. Date, meal session, menu, item, quantity, unit, responsible user (the
   recorder) and remarks are recorded. Met.
2. Confirmed issues reduce stock (one ISSUE movement per line). Met.
3. Draft issues change no stock (edit and cancel included). Met.
4. Linked to the meal session and menu; the link to a meal record waits
   for Stage 7 (S5). Partly met.
5. Unsupported issues are prevented: confirmation is refused when a
   balance would go below zero at any point, with the shortfall named.
   Met.

**STK03 — Unused stock returns: TESTED** (was PENDING).
1. Confirmed returns increase stock (UNUSED_RETURN movements). 2. Issued
and returned quantities stay separately visible on every issue line.
3. Net usage = issued − returned, shown per line. 4. Every return line
references its source issue line, and a return can never exceed it.

**AT01 — Stock movements and balance reconciliation: TESTED** (was
PENDING). Receipt → issue → unused return: the receipt posts once (a
second acceptance is refused), the issue lowers and the return restores
stock, and the ledger balance equals the displayed balance at every step
(`test_at01_receipt_issue_and_return_reconcile_with_the_ledger`; browser
walkthrough; the same flow on PostgreSQL against a copy of the development
data).

**Decisions applied.** 4b-1/4b-2: dated today, effective at confirmation;
backdated, at 23:59:59.999999 campus time on the date; a return never
before its issue. 4b-3: users with `consumption.update` confirm their own
drafts. 4b-4: KI-00001 / KR-00001 per campus (campus row locked). 4b-5:
the ledger is append-only — database triggers refuse UPDATE, DELETE and
TRUNCATE on `stock_movements` (for the superuser too), and every
application session refuses to change or delete a movement. S4:
reversals by ADMIN and KITCHEN_MANAGER only, whole document, with a
reason, a return before its issue. The form-options endpoint lets STAFF
with `consumption.*` use the forms without `menu.read` or
`inventory.read`; stock figures are shown only to `inventory.read`
holders. No permission, permission set or STAFF grant changed.

The one existing test that edited a movement
(`test_pur03_postgres.py::test_stock_log_days_are_campus_local`) now
inserts its own movement with the posting time it needs; the protection
was not weakened for it.

Master-data issue (documented, not changed): campus 1 has active meal
sessions "Breakfast" and "breakfast", plus "early morning"; the issue
forms list them as stored. Clean-up belongs to the master-data stage
(`REMAINING-WORK.md` stage 5).

Evidence:
- **Migration `c7d2e9f4a816` (M2b)** on a throwaway PostgreSQL 16 server
  (internal network, no published ports, no route to the development
  database; removed afterwards): empty database 7 of 7; restored copy of
  the development data 17 of 17 — UPDATE, UPDATE of a quantity, DELETE and
  TRUNCATE refused by the triggers, INSERT allowed, nothing kept; existing
  tables, movements, opening entries and STAFF grants unchanged; issue
  numbers unique per campus; status fields enforced; downgrade refused
  while kitchen issues exist; downgrade and re-upgrade; models and schema
  identical. The slice-4b API on that copy: 12 of 12 (STAFF #3 loads the
  forms, records and confirms their own issue, is refused reversals; an
  over-issue refused with the shortfall; return and reversals; campus
  isolation; a direct UPDATE refused).
- **Applied to the Docker development database** on 23 November 2026,
  `b5e1d7c3a920` → `c7d2e9f4a816`, from a one-off container, after a
  verified backup (`~/kitchen-copilot-backups/pre-c7d2e9f4a816-20261123-120237`,
  `pg_dump -Fc`, read back in full, 31 table-data entries). In application
  tables the migration wrote only the revision row; every table's row
  count, every movement column, user #3's 23 grants and all 26 STAFF
  grants were identical before and after. Both triggers installed and
  enabled.
- **Backend tests:** `test_kitchen_issues.py` 30 and
  `test_ledger_append_only.py` 9 (in-memory SQLite);
  `test_kitchen_issues_postgres.py` 11 (two confirmations racing for the
  last stock, one issue confirmed from four sessions, returns drafted at
  once, a return racing the issue's reversal, simultaneous numbering, the
  triggers for a superuser, the application guard, end-of-day storage).
  Full suite on PostgreSQL (`kitchen_copilot_test_db`): two runs, 564
  passed each (514 earlier + 50 new), 0 failed, 0 skipped, 0 errors; the
  PostgreSQL-only files (53 tests) five more times, 53 of 53 each.
- **Frontend:** unit tests 53 of 53 (7 new for the issue and return form
  rules); TypeScript, ESLint and the production build pass; generated API
  types regenerated from the running slice-4b API (77 paths), identical to
  an offline-schema generation.
- **Headless browser** against a SQLite-backed scratch API: 48 of 48, no
  page errors — new issue with session-filtered menus and validation,
  stock shown to ADMIN, over-issue refused with the shortfall, draft edit,
  confirmation, return with unit choice and limits, reversal order (return
  first), ledger and movement-log links to KI-/KR- numbers, cancelled
  draft, list and counts; KITCHEN_MANAGER; STAFF with `consumption.*` only
  (forms work, no stock figures, own draft confirmed, no reversal, API
  refuses reversal); STAFF with `consumption.read` only; STAFF without
  consumption codes; another campus; 390 px phone width on every screen
  and the return form.
- **Development API smoke test** (port 8000, read-only, after the apply):
  kitchen 24 of 24 (revision, both triggers enabled, lists and form
  options for ADMIN, KITCHEN_MANAGER and STAFF #3, meal sessions unchanged,
  stock pages); slice 4a stock 23 of 23; Stage 3 54 of 54. No application
  row was written during sync or smoke tests.

### Stage 4 slice 4c — physical counts and adjustments (23 November 2026)

Built to decisions S1, S2, S6 and the interim Q10 behaviour
(`STAGE-4-STOCK-PLAN.md` sections 4 and 10). With this slice every Stage 4
slice is complete. Nothing here is ACCEPTED.

**STK05 — Physical stock counts and adjustments: TESTED** (was PENDING).
1. A count preserves the system balance at count time, the physical
   quantity and the difference: the server takes the count time and the
   balance of each counted item while the items are locked, and stores
   them with the physical quantity (as entered and in the standard unit,
   with the factor used) and the difference (a database check keeps
   difference = physical − system balance). Met.
2. The verification date (count time), the verifier (the user who saves
   the count) and a reason (required) are recorded, with an audit row
   holding every line. Met.
3. The original count remains unchanged: no endpoint changes or deletes a
   count, every application session refuses to, and later movements,
   approvals and rejections leave its figures as they were. Met at the
   application level (no database trigger on counts; one would need
   approval).
4. Any adjustment is a separate movement: approval posts one ADJUSTMENT
   movement (source `ADJUSTMENT:<id>`), effective at the count time and
   created at approval, through the append-only ledger; earlier movements
   are untouched. Met.
5. An authorised ADMIN or KITCHEN_MANAGER who did not perform the count
   approves: STAFF are refused by role; the counter is refused by the API
   (403) and by the database (`decided_by <> counted_by`, with the counter
   copied through a composite foreign key). No fallback approver (Q10). Met.

**AT02 — Physical count and approved adjustment: TESTED** (was PENDING).
A count that differs from the system: the original system balance is
preserved; the physical count and reason are recorded; stock is unchanged
by the count and by raising the adjustment; the counter cannot approve;
another ADMIN or KITCHEN_MANAGER can, and the ledger then holds the counted
quantity (`test_at02_walkthrough` with a STAFF store keeper counting and the
KITCHEN_MANAGER approving; browser walkthrough with ADMIN counting and the
KITCHEN_MANAGER approving; the same on PostgreSQL against a copy of the
development data).

**STK04 — Stock balances and low-stock monitoring: TESTED** (was
IN_PROGRESS). Criteria 1–3 were met and tested in slice 4a and criterion 4
in slice 4b; it was kept IN_PROGRESS until every Stage 4 slice was complete
(your instruction of 23 November 2026). The slice 4a and 4b browser suites
were rerun against the slice 4c code (below).

**STK01 — Opening stock and stock ledger: IN_PROGRESS.** Criterion 3 now
covers receipts, opening stock, kitchen issues, unused returns, approved
adjustments and reversals; supplier returns wait for PUR05 (on hold for
client question Q6). Criterion 5 is met at the database level since slice
4b (append-only triggers).

**STK02 — Kitchen stock issues: IN_PROGRESS** (unchanged; the meal-record
link comes with Stage 7, S5).

**Movements between the count and the approval.** Movements effective
after the count time are kept and follow the adjustment in the ledger: the
balance at the count time becomes the counted quantity and today's balance
that quantity plus everything since
(`test_movements_after_the_count_are_kept_and_follow_the_adjustment`). A
movement dated on or before the count time but posted after it changes the
ledger at the count time, so raising and approving are refused and the item
is counted again (`test_a_backdated_movement_posted_after_the_count_blocks_approval`,
`test_raising_is_refused_once_the_ledger_at_the_count_time_changed`); the
same rule stops one difference being applied twice
(`test_a_second_count_cannot_apply_the_same_difference_twice`,
`test_an_adjustment_approved_while_another_count_waits_blocks_the_stale_one`).
A negative adjustment is refused if any later point would go below zero
(S2, `test_a_negative_adjustment_is_refused_if_later_history_would_go_below_zero`).

**Permissions.** Module `stock_count` (`stock_count.create`,
`stock_count.read`) added by M2c; both codes added to the KITCHEN_MANAGER
set and the STAFF-assignable list, as S1 states. No grant was inserted,
changed or deactivated; no other code moved in or out of any set. STAFF #3
holds no `stock_count` code and is refused the count screens and API.

**Found and fixed during verification: a deadlock.** The PostgreSQL race
tests failed intermittently (3 of 7 runs): document numbering locked the
campus row `FOR UPDATE`, which blocks the foreign-key check of a posting
that already held an item lock, while the numbering transaction waited for
that item. One request then failed with a server error and wrote nothing.
The same cycle existed since slice 4b (saving a draft issue while another
issue for the same item is confirmed). The numbering lock is now `FOR NO
KEY UPDATE` (one line in `next_number`); the new regression tests fail
against the old lock and pass with the new one (`STAGE-4-STOCK-PLAN.md`
section 10).

Evidence:
- **Migration `0e7d99065bd3` (M2c)** on a throwaway PostgreSQL 16 server
  (internal network, no published ports, no route to the development
  database; removed afterwards): empty database 14 of 14 checks; restored
  copy of the development data 36 of 36 — the three tables and the
  `stock_count` module with exactly two permission rows; every other
  table, every STAFF grant and every movement unchanged; no grant on the
  new codes; the append-only triggers and their function unchanged and
  still refusing UPDATE, DELETE and TRUNCATE after the upgrade, the
  downgrade and the re-upgrade; the counter-cannot-decide check (as
  superuser), the counter foreign key, the rejection-reason check, one
  PENDING per item, the difference check and unique count numbers;
  downgrade refused while counts or `stock_count` grants exist;
  downgrade and re-upgrade; models and schema identical. The final
  slice-4c API on a fresh copy: 15 of 15 (KITCHEN_MANAGER counts, the
  counter refused, ADMIN approves, the ledger names SC-00001, ADMIN as
  counter refused, rejection posts nothing, STAFF #3 refused, campus
  isolation, grants unchanged, a direct ledger UPDATE refused).
- **Applied to the Docker development database** on 23 November 2026,
  `c7d2e9f4a816` → `0e7d99065bd3`, from a one-off container, after a
  verified backup (`~/kitchen-copilot-backups/pre-0e7d99065bd3-20261123-190618`,
  `pg_dump -Fc`, read back in full, 35 table-data entries). In existing
  tables the migration wrote only the revision row, one module row and two
  permission rows: rebuilt with the old revision row, the content
  fingerprint of every other table equals the one taken before; the other
  26 permissions, user #3's 23 grants and all 26 STAFF grants are
  identical; no grant references the new codes. The triggers and their
  function are byte-for-byte unchanged and enabled. 37 tables, 120
  foreign keys.
- **Backend tests:** `test_stock_counts.py` 40 (in-memory SQLite: every
  STK05 criterion, AT02, blind entry, intervening movements, S2, Q10,
  permissions, campus isolation, lists, audit, master-data references) and
  `test_stock_counts_postgres.py` 13 (several approvers at once, approval
  racing rejection, a negative adjustment racing an issue, a count saved
  while an issue confirms, raises at once, numbering at once, the database
  rules for a superuser, append-only with approvals, a backdated issue
  blocking approval, the numbering lock, eight rounds of numbering and
  posting at once). Two existing test files updated for S1:
  `test_operational_authority.py` (the fixture seeds the new module) and
  `test_staff_permission_assignment.py` (the approved assignable list).
  Full suite on PostgreSQL (`kitchen_copilot_test_db`, final slice-4c
  code mounted read-only): two runs, 617 passed each (564 earlier + 53
  new), 0 failed, 0 skipped, 0 errors; the PostgreSQL-only files (66
  tests) five more times, 66 of 66 each.
- **Frontend:** unit tests 58 of 58 (5 new for the count entry rules);
  TypeScript, ESLint and the production build pass; generated API types
  (85 paths) identical to a generation from the running slice-4c API.
- **Headless browser** against a SQLite-backed scratch API, final code:
  57 of 57, no page errors — blind count sheet (no balance in the page or
  its data), validation, unit conversion, saved count with system balance,
  found and difference; raising with a reason; the counter waits and is
  refused by the API; KITCHEN_MANAGER sees the balance at count time then
  and now, today's balance, the balance after approval and the movements
  since the count, then approves (a later issue kept); the ledger names
  and links SC-00001; a late issue dated before the count blocks approval
  and the adjustment is rejected with nothing posted; a STAFF store keeper
  counts and raises but never decides and sees no current balances; a
  count-only STAFF user records counts and sees no balances; view-only
  STAFF; STAFF without codes; another campus; 390 px phone width on every
  new screen. The slice 4a (55 of 55) and 4b (48 of 48) browser suites
  pass against the slice-4c backend and build.
- **Development API smoke test** (port 8000, read-only, after the apply
  and code sync): counts 27 of 27 (revision, triggers, database rules,
  module and permissions, no grants, form options blind for ADMIN and
  KITCHEN_MANAGER, lists empty, KITCHEN_MANAGER codes, STAFF #3 refused,
  staff screen flags); kitchen 24 of 24; slice 4a stock 23 of 23; Stage 3
  54 of 54. No row was written during the sync or the smoke tests.

## 3. Meal Preparation and Distribution

| ID | Requirement | Status |
|---|---|---|
| MEAL01 | Student headcount records | TESTED |
| MEAL02 | Food preparation records | TESTED |
| MEAL03 | Food distribution records | TESTED |
| MEAL04 | Leftover tracking | TESTED |
| MEAL05 | Meal quantity reconciliation | TESTED |

### Stage 5 — meal records (23 November 2026)

Built to `STAGE-5-MEAL-PLAN.md` (decisions 5-1 to 5-10, approved 23 November
2026; closing needs `meal.update`, reopening is ADMIN and KITCHEN_MANAGER
with a reason and a full audit history). Nothing here is ACCEPTED. Rules
marked interim are not client decisions (plan section 6).

**MEAL01 — Daily meal sessions and headcounts: TESTED** (was IN_PROGRESS).
1. Each meal record is one meal session on one date (one live record per
   campus, date and session; database partial unique index). Met.
2. Expected students, staff and guests are recorded in separate fields. Met.
3. Actual people served are recorded after the meal (on or after its date),
   as the same three groups. Met.
4. Expected and actual stay in separate fields and are never derived from
   each other. Met.
Interim: expected counts up to 14 days ahead; actual counts by group
(client question on headcount collection). Meal sessions are used as
stored (C5 open; campus 1 still has "Breakfast", "breakfast" and "early
morning"). `daily_headcounts` and the dashboard are unchanged.

**MEAL02 — Record prepared dishes: IN_PROGRESS** (was PENDING).
1. Each dish has an output quantity (> 0) and a campus unit. Met.
2. Dishes belong to their meal record, so to its session and date. Met.
3. Ingredient issues are linked: the confirmed kitchen issues of the same
   campus, date and session, with issued, returned and net quantity. Met.
4. Planned requirements and actual net usage comparable: the actual side
   is built; the planned side waits for meal planning (versioned
   standards, client question Q3). Partly met.
Dish names are free text until the master-data stage adds prepared-food
items.

**MEAL03 — Record food distribution: TESTED** (was PENDING).
Available (output, or the carried quantity), distributed and remaining are
separate fields in the dish's unit; available = distributed + remaining is
checked by the API and the database; no headcount column exists on dishes
or leftovers, and counts never change food quantities (tested).

**MEAL04 — Classify leftovers: TESTED** (was PENDING), criterion 3 against
the interim process (Q11).
1. Retained, returned to supplier, wasted or otherwise disposed. Met.
2. Each with a quantity and remarks (required; database check). Met.
3. Retained food stays traceable when carried forward: carried once, whole,
   into a later record as its own dish line, with the source meal, dish,
   leftover, quantity and unit kept; the source is locked while carried
   (API; composite foreign key on PostgreSQL). Met for the interim process
   until client question Q11 is answered.
4. Retained food is never a purchase: no purchase, receipt, stock movement,
   supplier return, credit or payment is created by any meal action
   (tested on SQLite and PostgreSQL). Met.
"Returned to supplier" is a classification only (Q6); no waste record is
created (the waste screen says not to enter meal leftovers again).

**MEAL05 — Reconcile food quantities: TESTED** (was PENDING).
1. Available = distributed + remaining (API message with the numbers;
   database check). Met.
2. Leftovers add up exactly to the remaining quantity before closing;
   partial classification is refused. Met.
3. Nothing counted twice: one leftover line per classification per dish,
   each retained line carried at most once (database unique constraints),
   and a carried quantity equals its source. Met.
4. Invalid or inconsistent quantities are refused with a clear message
   (API and screens). Met.

**STK02 — Kitchen stock issues: TESTED** (was IN_PROGRESS). Criterion 4
(linked to the relevant meal record) is now met: each issue shows the meal
record of its date and session, and the meal record lists its issues with
net usage (`test_meal02_ingredient_issues_of_the_same_date_and_session_are_linked_with_actual_net_usage`;
browser). Criteria 1–3 and 5 were met in slice 4b.

**Permissions and corrections.** Module `meal` (`meal.read`, `meal.create`,
`meal.update`) added by M5, in the KITCHEN_MANAGER set and the
STAFF-assignable list; no grant inserted, changed or deactivated. STAFF
with `meal.update` edit, close and cancel OPEN records only; a CLOSED or
CANCELLED record refuses every change; reopening (reason required) and the
history are ADMIN and KITCHEN_MANAGER only (interim rule for historical
corrections). Every action is an audit row; each closing keeps a snapshot
and each reopening who, when and why.

Evidence:
- **Migration `ea00e5387c2f` (M5)** on a throwaway PostgreSQL 16 server
  (internal network, no published ports, no route to the development
  database; removed afterwards): empty database 14 of 14 checks; restored
  copy of the development data 40 of 40 — the three tables and the `meal`
  module with exactly three permission rows; every other table, every
  STAFF grant and every movement unchanged; no grant on the new codes; the
  ledger triggers and their function unchanged and still refusing UPDATE,
  DELETE and TRUNCATE after the upgrade, the downgrade and the re-upgrade;
  a carried source's quantity cannot change and it cannot be deleted (as
  superuser), one carry per retained line, a carried quantity equals its
  source, available = distributed + remaining, leftovers in their dish's
  unit, one live record per session, a closed record has its actual
  counts, reopening fields complete; downgrade refused while meal records
  or meal grants exist; downgrade and re-upgrade; models and schema
  identical. The Stage 5 API on that copy: 17 of 17.
- **Applied to the Docker development database** on 23 November 2026,
  `0e7d99065bd3` → `ea00e5387c2f`, from a one-off container, after a
  verified backup (`~/kitchen-copilot-backups/pre-ea00e5387c2f-20261123-223907`,
  `pg_dump -Fc`, read back in full, 38 table-data entries). In existing
  tables the migration wrote only the revision row, one module row and
  three permission rows (per-table write counters; with the old revision
  row the content fingerprint of every other table equals the one taken
  before). The other 28 permissions, user #3's 23 grants and all 26 STAFF
  grants are identical; no grant references the meal codes; the ledger
  triggers and function are unchanged and enabled. 40 tables, 139 foreign
  keys. No row was written during the code sync or the smoke tests.
- **Backend tests:** `test_meals.py` 29 (in-memory SQLite: every MEAL
  criterion, carry-forward rules, locks, closed records, reopening,
  history, permissions for each role and code, campus isolation, issues
  changed after closing, no stock or money rows, master-data references)
  and `test_meals_postgres.py` 15 (two records for one session at once,
  closing twice at once, a change racing the close over four rounds, one
  retained line carried into two records at once, a carry racing the
  reopening of its source, eight database rules for a superuser, no stock
  movement). Two existing test files updated for decision 5-1
  (`test_operational_authority.py` seeds the module and drops its SQLite
  tables with foreign keys off; `test_staff_permission_assignment.py`
  lists the approved assignable codes). Full suite on PostgreSQL
  (`kitchen_copilot_test_db`, final Stage 5 code mounted read-only): two
  runs, 661 passed each (617 earlier + 44 new), 0 failed, 0 skipped,
  0 errors; the PostgreSQL-only files (81 tests) five more times, 81 of 81
  each.
- **Frontend:** unit tests 64 of 64 (6 new for the meal entry rules);
  TypeScript, ESLint and the production build pass; generated API types
  (98 paths) identical to a generation from the running Stage 5 API.
- **Headless browser** against a SQLite-backed scratch API, final code:
  54 of 54, no page errors — new record with validation and date default;
  linked issue and net usage; separate expected and actual counts;
  dishes with output, unit and menu; distribution refused until available
  = distributed + remaining and leftovers add up; closing refused until
  everything reconciles, then read-only; retained food carried once into
  Dinner as its own dish; the kitchen issue links its meal record;
  KITCHEN_MANAGER reopens with a required reason, the carried line stays
  locked, re-closes; issues changed after closing are flagged; the
  history lists every step; STAFF with the three codes records and closes
  but cannot reopen or see the history; view-only STAFF; create-only STAFF
  ("Record a Meal"); STAFF without codes; another campus; 390 px phone
  width on every screen and the distribution form. Stage 4 regression on
  the Stage 5 backend and build: slice 4a 55 of 55, 4b 48 of 48, 4c 57 of
  57.
- **Development API smoke test** (port 8000, read-only, after the apply
  and code sync): meals 26 of 26; counts 27 of 27; kitchen 24 of 24; stock
  23 of 23; Stage 3 54 of 54.
- **Found while building:** carrying a record's own retained food into
  itself crashed (500) instead of being refused; fixed before any run on
  PostgreSQL. On SQLite, SQLAlchemy does not always create the added-later
  carried-from foreign key after PostgreSQL tests ran in the same process,
  so that database-level lock is asserted on PostgreSQL only.

## 4. Outsourced Food Management

| ID | Requirement | Status |
|---|---|---|
| OUT01 | Outsourced food tracking | TESTED |
| OUT02 | Outsourced food reporting | TESTED |
| OUT03 | Rejected deliveries and supplier returns | IN_PROGRESS |

### Stage 8a — outsourced food (24 November 2026)

Built to `STAGE-8-IMPLEMENTATION-PLAN.md` (project decisions P8-1 to P8-5
and P8-7, section 12 "As built"); migration M6 (`b8e4c2a9d175`). Nothing
here is ACCEPTED. Rules marked interim are not client decisions: who orders
and who sees costs (matrix gap, P8-3 option b); rejected food with no credit
(Q6); exact meal-session matching (C5); explicit units (Q7); closed meal
records never changed (proposal §4.2). Stage 8b (supplier returns and
credits, PUR05, OUT03 criteria 2–4) waits for Q6; P8-6 (outsourced items in
plans) is deferred.

**OUT01 — Track outsourced food separately: TESTED** (was PENDING).
1. Date, meal session, food item and supplier: an outsourced order has the
   order date, meal date, exact meal session and supplier; its lines are
   OUTSOURCED items only. Met.
2. Ordered and received separately: ordered per order line; received,
   rejected and accepted per delivery line (accepted = received −
   rejected, database check), partial deliveries allowed, accepted never
   more than ordered. Met.
3. Unit, unit rate and total cost: explicit unit, rate and line total
   (planned cost) per order line; the bill line linked to it carries the
   billed cost. Met.
4. Distributed and remaining: accepted food becomes a "received" dish line
   on the meal record of the same campus, date and session, where
   distributed + remaining = received (Stage 5 rules). Met.
5. Retained, returned, wasted, other disposal: the Stage 5 leftover
   classification on received lines (returned to supplier is a
   classification only; no credit, Q6). Met.
6. Costs linked to source purchase records: one supplier bill line per
   order line (same supplier, item and unit; database unique). Met.
7. Separate from raw stock: no stock movement, goods receipt, opening,
   issue, count or adjustment for OUTSOURCED items — refused by receipts,
   kitchen issues, opening stock, counts and the stock ledger itself; an
   item with stock movements cannot be classified OUTSOURCED (P8-5).
   Table contents compared before and after the whole workflow on SQLite,
   PostgreSQL and the throwaway copy. Met.
Evidence: `tests/test_outsourced.py` (32), `tests/test_outsourced_postgres.py`
(8), throwaway copy (`api_on_copy_8.py`, 33 checks), browser suite (66
checks).

**OUT02 — Outsourced food reports: TESTED** (was PENDING).
1. Daily, weekly, monthly and custom: presets Today, This week (from
   Monday), This month, Custom (up to 366 days). Met.
2. Received, distributed and leftover quantities: per line, per item and
   per unit (no conversion), with retained, returned, wasted and disposed.
   Met.
3. Purchase expenditure: from linked bill lines only; the planned (order)
   cost is shown separately and never added; costs only for users with
   `purchase_bill.read`. Met.
4. Filters by item, supplier and meal session (exact session). Met.
Excel and PDF exports (audited) and a print view reuse the purchases
report patterns.

**OUT03 — Rejected deliveries and supplier returns: IN_PROGRESS** (was
PENDING).
1. Rejected quantities recorded separately: per delivery line, with a
   required reason, shown on the order, the meal record and the report with
   "Credit not recorded because client question Q6 … remains unresolved".
   Met.
2–4. Supplier returns referencing their source, no double counting of
   returns, traceable credits: not built — Stage 8b, waiting for Q6 (PUR05
   on hold). Deliveries themselves never post stock and the planned cost is
   never added to expenditure.

**AT04 — Outsourced breakfast report: TESTED** (was PENDING). An order for
Breakfast, a linked bill line, a delivery with a rejection, the meal
record's distribution and leftovers: the report shows received (100),
rejected (6), accepted (94), distributed (85), leftovers (4 retained, 2
returned, 3 wasted), the line reconciles, and the linked purchase cost
(₹3,550.00) is shown apart from the planned cost
(`test_report_reconciles_quantities_and_shows_linked_cost`; throwaway copy;
browser). Which meals are outsourced (client questions §6.1) and the
"Breakfast" / "breakfast" sessions (C5) remain open: sessions are matched
exactly.

**PLAN08 — Planned versus actual: TESTED** (was IN_PROGRESS). Criterion 3
("prepared or received food quantities") is now met for received food:
the planning panel lists received outsourced lines as their own kind with
the received quantity (`test_planned_vs_actual_shows_received_outsourced_food`).
Outsourced items stay unplannable (P8-6 deferred).

## 5. Quantity Planning

| ID | Requirement | Status |
|---|---|---|
| PLAN01 | Headcount-based meal planning | TESTED |
| PLAN02 | Per-person ingredient standards | TESTED |
| PLAN03 | Historical planning suggestions | TESTED |
| PLAN04 | Automatic quantity recalculation | TESTED |
| PLAN05 | Procurement gap calculation | TESTED |
| PLAN06 | Manual overrides and versioning | TESTED |
| PLAN07 | Planning separate from actual stock | TESTED |
| PLAN08 | Planned-versus-actual comparison | TESTED |

### Stage 6 — meal planning (24 November 2026)

Built to `STAGE-6-PLANNING-PLAN.md` (decisions 6-1 to 6-9, safeguards S6-1
to S6-6 and the section 12 choices, approved 24 November 2026). Nothing
here is ACCEPTED. Rules marked interim are not client decisions (plan
section 11: Q3, client questions §5.1–§5.3, Q7/Q8, Q2, C5, §4.2, Q11,
the matrix gap for who creates plans).

**PLAN01 — Create a meal plan: TESTED** (was PENDING).
1. A plan has a date (today or later), meal session, menu of that session
   and expected headcount (≥ 1). Met.
2. Only the main items needed are chosen (any subset of the menu's items
   with an approved standard). Met.
3. Entering every recipe ingredient is not compulsory. Met.

**PLAN02 — Define per-person standards: TESTED** (was PENDING).
1. Per-person quantities per menu and item, created, edited as drafts and
   approved by ADMIN or KITCHEN_MANAGER (interim, Q3). Met.
2. Items are identified as raw or prepared: `items.item_kind`, set only by
   ADMIN and KITCHEN_MANAGER (decision 6-8; refused for STAFF whatever
   `inventory.*` grants they hold, and refused through the item forms); a
   standard is approved only for a RAW or PREPARED item. Met.
3. Different menus may use different standards for the same item (rice
   150 g for Veg Biryani, 0.12 kg for Dal Fry). Met.
4. Weight- and count-based quantities (g, kg, pc, dozen), with units
   limited to explicit conversion records (S6-3; weight-to-piece refused).
   Met.

**PLAN03 — Suggest standards from historical usage: TESTED** (was PENDING).
1. Suggested per person = total net usage ÷ total actual people served
   (6 kg ÷ 123 = 0.04878 kg = 48.78 g). Met.
2. The user selects the closed meal records. Met.
3. Only valid records in compatible units are used: not closed, cancelled,
   no actual counts, no people served, no usage of the item, or usage in
   another unit are listed as excluded with the reason. Met.
4. Presented for review (preview with totals and exclusions). Met.
5. Saved only as a DRAFT with its basis records; applied after an ADMIN or
   KITCHEN_MANAGER approves it; the basis rows can never change (trigger).
   Met.

**PLAN04 — Recalculate quantities immediately: TESTED** (was PENDING).
1. Required = expected headcount × approved quantity per person (AT05).
   Met.
2. Recalculates when the headcount changes (on screen while typing, and
   by the API). Met.
3. Recalculates when a standard changes: a DRAFT plan follows the version
   in effect on its date (decision 6-6). Met.
4. Gram-to-kilogram display (90,000 g = 90 kg) through the explicit
   g → kg record. Met.
5. Count-based quantities round up to whole pieces (451 × 0.5 = 226 pc).
   Met.
6. Saved (approved) plans keep the standard, quantity per person, factor
   and required quantities used: snapshot at approval, never changed
   (API and database triggers, S6-2). Met.

**PLAN05 — Stock and procurement gap: TESTED** (was PENDING).
Required quantity, current stock and additional quantity =
max(0, required − current stock) are shown per item in the item's stock
unit, labelled "Current availability (today's stock balance), not a
forecast"; quantities on order are not counted. Met (rice 67.5 kg needed,
30 kg in stock, 37.5 kg to buy; 15 kg needed with 20 kg in stock gives 0).

**PLAN06 — One-day overrides and versioned standards: TESTED** (was PENDING).
1. An override needs a quantity, a unit and a reason (API and database
   check). Met.
2. It applies only to that plan (another plan for the same menu keeps the
   standard). Met.
3. Standards have effective dates (today or later; section 12 choice 2);
   the latest effective date on or before the plan date wins, then the
   highest version. Met.
4. Older approved plans keep their values when a newer version is
   approved (AT06). Met.
5. Every create, change, copy, suggestion, approval, cancellation and
   item-kind change is an audit row (entities `PORTION_STANDARD`,
   `MEAL_PLAN`, `ITEM` `SET_KIND`), shown as history. Met.

**PLAN07 — Planning separate from stock: TESTED** (was PENDING).
Creating, editing, approving and cancelling plans and standards writes no
stock movement, kitchen issue or return, count, adjustment, purchase
order, bill, receipt, supplier payment or supplier return: table contents
compared before and after on SQLite and PostgreSQL, on the throwaway copy
of the development data, and in the browser (rice stays 30 kg); a static
test checks that the planning code imports none of those models (S6-5).
Met.

**PLAN08 — Planned versus actual: IN_PROGRESS** (was PENDING; decision 6-9).
Built for meals cooked in-house, against the meal record of the exact
campus, date and meal session (S6-1): planned quantity per item against
actual net usage (at closing once the record is closed), difference,
planned and actual per person; planned, expected and actual headcounts;
prepared output, carried retained food shown separately (interim, Q11),
distributed and leftovers by classification. Criterion 3 ("prepared or
received food quantities") is met for prepared food only; received
(outsourced) quantities come with the outsourced-food stage.

**MEAL02 — Record prepared dishes: TESTED** (was IN_PROGRESS). Criterion 4
(planned requirements and actual net usage comparable) is now met: the
meal record page shows the plan of its exact date and session with planned
against actual usage for ADMIN and KITCHEN_MANAGER (STAFF who may read meal
records do not see planning) (`test_plan08_plan_vs_actual_on_the_plan_and_the_meal_record`;
browser). Criteria 1–3 were met in Stage 5.

**Safeguards.** S6-1: plans and meal records link only on the exact
`meal_session_id`; a record or plan in a same-named session ("Breakfast" /
"breakfast" on campus 1, C5) is reported and never linked or used to
pre-fill. S6-2: approved and cancelled standards and plans, suggestion
basis rows and the lines of non-draft plans are refused by the API and by
four database triggers. S6-3: explicit conversion records only; units and
conversions used by standards and plan lines become frozen. S6-4: copying
menu main items creates drafts only (menu main items unchanged), each
approved separately. S6-5: see PLAN07. S6-6: interim rules and open
questions are listed in the plan (section 11) and on the screens.

**Permissions.** Modules `portion_standard` and `meal_plan` (create, read,
update) added by M4, in the KITCHEN_MANAGER set, not STAFF-assignable
(6-3); every planning endpoint also requires the ADMIN or KITCHEN_MANAGER
role, so STAFF are refused whatever grants exist; approving and setting
the item kind are role checks. No grant was inserted, changed or
deactivated.

Evidence:
- **Migration `f3a8c2d61b47` (M4)** on a throwaway PostgreSQL 16 server
  (internal network, no published ports, no route to the development
  database; removed afterwards): empty database 17 of 17 checks; restored
  copy of the development data 44 of 44 — the four tables, `items.item_kind`
  with no item classified, the two modules with exactly six permission
  rows; every pre-existing table unchanged in every pre-existing column
  (grants and menu main items included); no grant on the new codes; the
  ledger triggers and function unchanged and still refusing UPDATE, DELETE
  and TRUNCATE after the upgrade, the downgrade and the re-upgrade; the
  four planning triggers installed; as superuser an approved standard
  cannot change, a standard or plan is never deleted, an approved plan and
  its lines cannot change, one live plan per session, `ck_item_kind`;
  downgrade refused while a classified item, a standard or a planning grant
  exists; downgrade and re-upgrade; models and schema identical. The
  Stage 6 API on that copy: 26 of 26 (Monday Lunch for 450: rice 67.5 kg,
  onion 9 kg, tomato 13.5 kg; gaps against the real balances; STAFF #3
  refused; the real "Breakfast"/"breakfast" sessions reported, not linked).
- **Applied to the Docker development database** on 24 November 2026,
  `ea00e5387c2f` → `f3a8c2d61b47`, from a one-off container, after a
  verified backup (`~/kitchen-copilot-backups/pre-f3a8c2d61b47-20261124-113558`,
  `pg_dump -Fc`, 215,255 bytes, read back in full, 41 table-data entries).
  In existing tables the migration wrote only the revision row, two module
  rows and six permission rows (per-table write counters); with the old
  revision row the content fingerprint of every pre-existing table over its
  pre-M4 columns equals the one taken before (`b5bb1534…`). Items (123),
  menu main items (48) and stock movements (6) are unchanged; no item is
  classified; the other 31 permissions, user #3's 23 grants and all 26 STAFF
  grants are identical; no grant references the planning codes; the ledger
  triggers and function are unchanged and enabled; the four planning
  triggers are enabled. 44 tables, 164 foreign keys. No row was written
  during the code sync or the smoke tests.
- **Backend tests:** `test_planning.py` 24 (in-memory SQLite: item kind by
  role only and never through the item forms or older STAFF grants; every
  PLAN criterion; AT05 and AT06; S6-1 to S6-5; database triggers; four
  roles, campus isolation; frozen units and conversions; the migration's
  trigger SQL equals the models') and `test_planning_postgres.py` 10 (the
  PostgreSQL triggers and check constraints for a superuser; two plans for
  one slot at once; one standard approved four times at once; four versions
  approved at once get versions 1–4; approve racing cancel; copying a menu
  twice at once; no stock, purchasing or supplier row; a STAFF
  `inventory.update` grant never classifies). One existing test file
  updated (`test_operational_authority.py` seeds the two modules). Full
  suite on PostgreSQL (`kitchen_copilot_test_db`, final Stage 6 code
  mounted read-only): two runs, 695 passed each (661 earlier + 34 new),
  0 failed, 0 skipped, 0 errors; the nine PostgreSQL-only files (91 tests)
  five more times, 91 of 91 each. An earlier full run had 694 passed and
  1 failed: the Mac idle-slept from 09:05:24 to 09:40:22 (power log) during
  `test_rejection_posts_nothing_keeps_the_reason_and_needs_a_new_count`,
  so its 30-minute access token expired between two requests; the file
  passed 40 of 40 on its own, later runs used `caffeinate -i`, and neither
  the tests nor authentication were changed.
- **Frontend:** unit tests 70 of 70 (6 new for the planning arithmetic);
  TypeScript, ESLint and the production build pass; generated API types
  (115 paths) identical to a generation from the running Stage 6 API.
- **Headless browser** against a SQLite-backed scratch API, final code:
  51 of 51, no page errors — item classification by KITCHEN_MANAGER and the
  kind column; the menu-main-items notice; copying a menu creates two
  drafts only; approval makes version 1 in effect with no edit controls;
  units for eggs limited to count units; a new plan with immediate
  recalculation (AT05 figures, gap, 226 pc rounded up), an override refused
  without a reason, saved and approved, frozen, refused by the API, no stock
  movement; cancel and replace with history; the same-named session warning
  and the unlinked "breakfast" record; plan versus actual on the meal
  record; a suggestion of 48.78 g saved as a draft with its basis; 390 px
  phone width on all six screens; STAFF with older grants sees no planning,
  cannot classify, is sent back from the address and refused by the API;
  another campus. Regression on the Stage 6 backend and build: slice 4a
  55 of 55, 4b 48 of 48, 4c 57 of 57, Stage 5 meals 54 of 54.
- **Development API smoke test** (port 8000, read-only, after the apply
  and code sync): planning 40 of 40; meals 26 of 26; counts 27 of 27;
  kitchen 24 of 24; stock 23 of 23; Stage 3 54 of 54.

## 6. Dashboard and Reports

| ID | Requirement | Status |
|---|---|---|
| DASH01 | Dashboard filters | TESTED |
| DASH02 | Price and quantity decomposition | TESTED |
| DASH03 | Like-for-like unit comparison | TESTED |
| DASH04 | Partial-month comparison | TESTED |
| DASH05 | Report drilldown | TESTED |

### Evidence (26 November 2026, Stage 9)

TESTED, not ACCEPTED. `services/api/tests/test_stage9_dashboard_reports.py`
(10 tests) with `test_dashboard.py` (16 together): comparison periods
(elapsed, full months, previous period; multi-month periods do not overlap),
weighted average prices, price effect (P1 − P0) × Q1 and quantity effect
(Q1 − Q0) × P0, lines without an explicit conversion excluded and counted,
"Not comparable" when the earlier value is 0, campus isolation, financial
figures only with `purchase_bill.read`, every report's Excel and PDF export
audited. AT03 uses the interim rule for Q4: one transaction = one supplier
bill; purchase days = distinct bill dates. Dashboard headcount comes from
meal records only. Live read-only browser check on the development site:
45 of 46; the failure (re-selecting the report already shown cleared it)
was fixed and is re-checked with the Stage 10/12 live check (desktop and
390 px phone; ADMIN, STAFF with and without grants).

## 7. Cross-Cutting Requirements

| Area | Requirement | Status |
|---|---|---|
| Authentication | Secure login and session management | TESTED |
| Authorisation | Four roles and permissions | IN_PROGRESS (ADMIN, KITCHEN_MANAGER, STAFF tested; SUPER_ADMIN prepared as migration `d5e8f0b2a314`, awaiting authorization) |
| Campus isolation | Campus-scoped data access | TESTED |
| Audit | Record important user activities | TESTED (Audit Log viewer, Stage 10) |
| Reports | Export and print support | TESTED |
| AI | Controlled agent and approval workflows | TESTED (FakeLLM and built-in reader; `AGENT_ENABLED=false` by default; no live model) |
| Security | Protect sensitive operational information | TESTED (interim Q19 sign-in throttling; session revocation; money hidden without `purchase_bill.read`) |

Stages 10 and 12 (26 November 2026): migration `c4d7e9a1f203` applied to
the development database after a verified backup (all existing rows,
STAFF grants, permissions and ledger triggers unchanged). Evidence:
`services/api/tests/test_stage10_12.py`, full backend suite 767 passed,
migration round trip 14 of 14 (`docs/STAGE-10-12-NOTES.md`).

## 8. Acceptance Tests

| ID | Acceptance scenario | Status |
|---|---|---|
| AT01 | Stock movements and balance reconciliation | TESTED |
| AT02 | Physical count and approved adjustment | TESTED |
| AT03 | Monthly purchase reporting | TESTED (interim Q4 rule) |
| AT04 | Outsourced food reconciliation | TESTED |
| AT05 | Headcount-based quantity calculation | TESTED |
| AT06 | Historical standard preservation | TESTED |
| AT07 | Price and quantity comparison | TESTED |
| AT08 | Supplier payment reconciliation and exports | TESTED |

## 9. Status Definitions

- PENDING: No verified implementation of the requirement yet.
- IN_PROGRESS: Some implementation exists, but the complete requirement is not finished.
- IMPLEMENTED: The complete requirement has been implemented.
- TESTED: The implemented requirement has passed its relevant verification tests.
- ACCEPTED: The delivered requirement has been confirmed by the client.

A requirement must not be marked IMPLEMENTED or TESTED without supporting evidence. ACCEPTED requires client confirmation.

Approval of the project proposal and permission matrix on 05 November 2026 does not automatically mean individual requirements have been implemented, tested, or accepted.

The Week 1 development milestone does not represent completion or production acceptance of the entire Kitchen Copilot system.

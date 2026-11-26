# Kitchen Copilot — Stage 6 Completion and Client Review Report

## Meal Planning (PLAN01–PLAN08, AT05, AT06)

| | |
|---|---|
| Project | Kitchen Copilot — Kitchen and Mess Management System |
| Client | Zaitoon International Girls Campus, Payyanur |
| Stage | 6 — Meal planning (headcount-based quantity planning and versioned portion standards) |
| Report date | 24 November 2026 |
| Stage status | Built and tested on the development system. **Not yet accepted by the client.** |
| Database revision | `f3a8c2d61b47` (migration M4), applied to the Docker development database on 24 November 2026 |
| Environment | Development only. Nothing has been deployed to a production or client environment |
| Source documents | `PROPOSAL.md` §5.5, §14; `STAGE-6-PLANNING-PLAN.md`; `REQUIREMENTS-TRACEABILITY.md`; `diagrams/ERD.md`; `REMAINING-WORK.md`; `DEVELOPMENT-SAFETY.md` |

---

## 1. Summary

Stage 6 adds meal planning to Kitchen Copilot. A Kitchen Manager or Admin
can now:

- keep approved, dated per-person quantities ("portion standards") for
  each menu and main item;
- plan a meal from a date, meal session, menu and expected headcount,
  with required quantities calculated straight away;
- see current stock and the quantity still to buy;
- compare the plan with what was actually used and served once the meal
  is recorded.

Planning never changes stock and never creates a purchase.

All agreed checks pass on the final code: backend, frontend, browser,
migration and API tests, plus a read-only check of the running
development system. The database change was applied to the development
database after a verified backup, and it changed no existing record.

| Requirement | Status |
|---|---|
| PLAN01–PLAN07 | TESTED |
| AT05, AT06 | TESTED |
| MEAL02 | TESTED (its last criterion completed in this stage) |
| PLAN08 | IN_PROGRESS — the outsourced-food part waits for Stage 8 |

**Nothing is ACCEPTED.** Acceptance needs the client's review and
confirmation (section 10).

---

## 2. Scope

### In scope (approved 24 November 2026)

- Meal planning: PLAN01–PLAN08, and acceptance tests AT05 and AT06.
- The remaining criterion of MEAL02 (planned requirements compared with
  actual usage).
- From the master-data backlog, only the **item kind** (raw, prepared or
  outsourced), which PLAN02 needs.

### Not in scope

- Searching items and suppliers as you type, and cleaning up duplicate
  meal sessions (client question C5).
- Supplier returns (PUR05, client question Q6).
- Outsourced food (Stage 8).
- Reports and exports.
- The AI "plan and procure" job.

The decisions that shaped this stage are numbered 6-1 to 6-9, with
safeguards S6-1 to S6-6 and seven implementation choices. They were
approved for the project on 24 November 2026 and are recorded in
`STAGE-6-PLANNING-PLAN.md`. They are project decisions, not client
business rules. Where a client question is still open, the rule used is
marked **interim** (section 8).

---

## 3. Delivered features

### 3.1 Item kind (raw, prepared, outsourced)

- Each item can be classified as raw, prepared or outsourced (proposal
  §5.7).
- **Only Admins and Kitchen Managers can set or change it.** Staff
  cannot, whatever older permissions they hold, and the normal item form
  cannot change it either.
- Existing items start as "Not classified"; nothing was filled in
  automatically.
- A kind can be changed but not cleared, and every change is recorded in
  the audit history.

### 3.2 Portion standards (Menu Planning → Portion Standards)

- **Per-person quantities** are set per menu and item, by weight (g, kg)
  or by count (pieces). The same item can have different quantities on
  different menus.
- **Draft, then approval:** a standard is used only after an Admin or
  Kitchen Manager approves it.
- **Approved standards never change.** To change a quantity, approve a
  new version with an effective date:
  - plans dated on or after that date use the new version;
  - plans approved earlier keep their original figures;
  - if two versions share a date, the one approved later wins.
- **Effective dates** are today or later; standards cannot be back-dated.
- **Copy from a menu:** the existing "menu main items" can be copied into
  draft standards. They are never approved automatically, and the menu
  main items themselves are not changed. The Menu Main Items screen now
  says "Not used by planning".
- **Suggest from past meals (PLAN03):**
  - average per person = total quantity used ÷ total people served, over
    closed meal records the user chooses;
  - records that cannot be used are listed with the reason;
  - the result is saved as a draft and needs approval.
- **Units:** only units with an explicit conversion record to the item's
  stock unit can be chosen. Weight-to-piece is never assumed.

### 3.3 Meal plans (Menu Planning → Meal Plans)

- **Creating a plan:** choose the date (today or later), meal session,
  menu and expected headcount, then tick only the main items needed.
- **Calculation:** required quantity = headcount × the approved quantity
  per person. It recalculates while you type.
  - Count items round up to whole pieces (for example 451 × 0.5 egg = 226
    eggs).
  - Grams are also shown in kilograms (for example 90,000 g = 90 kg).
- **Stock gap:** each item shows current stock and the quantity still to
  buy, max(0, required − current stock). It is labelled "current
  availability, not a forecast".
- **One-day overrides:** a different quantity for one plan only. It needs
  a reason, and the standard itself is not changed.
- **Draft and approval:**
  - a draft follows the standard in effect on its date;
  - approval by an Admin or Kitchen Manager freezes the plan with the
    exact figures and standard versions used;
  - an approved plan is corrected by cancelling it with a reason and
    creating a new one, and the cancelled figures stay as history.
- **History:** every create, change, approval and cancellation is shown.
- **One plan per slot:** one live plan per campus, date and meal session.

### 3.4 Planned versus actual (PLAN08, MEAL02)

On the meal plan, and on the meal record of the same date and session, the
system compares:

- each item's planned quantity with its actual net usage (kitchen issues
  minus unused returns), and the per-person figures;
- the planned, expected and actual headcounts;
- prepared output, distribution and leftovers, with carried-over retained
  food shown separately.

This comparison is shown to Admins and Kitchen Managers.

### 3.5 Safeguards

| Safeguard | How it works |
|---|---|
| S6-1 Meal-session matching | A plan links to a meal record only when the meal session is exactly the same. Campus 1 has both "Breakfast" and "breakfast"; a record in the other spelling is shown as a warning and never linked or used for the headcount |
| S6-2 Approved records never change | Enforced by the application and by four database triggers that also stop direct database changes |
| S6-3 Explicit conversions only | Units without an approved conversion record are refused; conversions and units used by plans become fixed |
| S6-4 No automatic approval | Copied and suggested standards are always drafts |
| S6-5 No stock or purchasing effect | Planning never creates or changes stock movements, issues, returns, counts, adjustments, purchase orders, bills, receipts, supplier payments or supplier returns |
| S6-6 Open questions documented | Interim rules are listed in the plan, in this report and on the screens |

---

## 4. Database migration M4 and backup

### 4.1 Migration `f3a8c2d61b47` (M4)

The migration only adds; it changes no existing record.

- **One new column:** `items.item_kind`, optional, with a database check
  that allows only raw, prepared or outsourced.
- **Four new tables:**
  - `portion_standards` — versioned per-person quantities;
  - `portion_standard_basis` — the meal records behind a suggested
    standard;
  - `meal_plans` — one live plan per campus, date and session;
  - `meal_plan_lines` — main items, one-day overrides, and the figures
    frozen at approval.
- **Four triggers** that keep approved standards and plans unchanged
  (S6-2).
- **Permissions:** two permission groups, "Portion Standards" and "Meal
  Plans", each with create, read and update. No permission was granted
  to anyone.
- **Undoing it:** the migration refuses to be undone while any planning
  data, classified item or planning permission grant exists.

### 4.2 Verification before applying

The migration was tested on a temporary PostgreSQL 16 server with no
outside network access and no route to the development database. The
server was removed afterwards.

| Check | Result |
|---|---|
| Install, remove and reinstall on an empty database | 17 of 17 checks passed |
| The same on a restored copy of the development data | 44 of 44 checks passed |
| The Stage 6 API working against that copy | 26 of 26 checks passed |

The copy checks confirmed:

- every existing table was unchanged in every existing column, including
  menu main items and Staff permissions;
- no item was classified;
- the stock ledger protections still worked;
- the new database rules and the undo guard worked;
- the database structure matched the application code exactly.

The API check on the copy planned Monday Lunch for 450 people: rice
67.5 kg, onion 9 kg, tomato 13.5 kg, against the real stock balances.

### 4.3 Backup and application to the development database

| Item | Detail |
|---|---|
| Backup | `~/kitchen-copilot-backups/pre-f3a8c2d61b47-20261124-113558/docker_kitchen_copilot_db.dump` |
| Backup check | Full PostgreSQL custom-format dump (`pg_dump -Fc`), 215,255 bytes, SHA-256 starting `8cab6602da8b7f64`; read back in full with no error; 41 table-data entries |
| Applied | 24 November 2026, from `ea00e5387c2f` to `f3a8c2d61b47`, using a one-off container |
| What it wrote to existing tables | The migration revision row, 2 permission-group rows and 6 permission rows. Nothing else |
| Proof that nothing else changed | With the old revision row put back, the content fingerprint of every existing table (over its original columns) equals the one taken before the change |
| Unchanged | Items (123), menu main items (48), stock movements (6), all Staff permission grants, the stock ledger protections |
| Database after the change | 44 tables, 164 foreign keys; the four planning triggers enabled |
| After the code update and checks | No database row was written |

---

## 5. Test results

All results are for the final Stage 6 code.

| Area | Result |
|---|---|
| New backend tests | 24 (SQLite) and 10 (PostgreSQL), all passing |
| Full backend test suite on PostgreSQL | 2 clean runs, **695 of 695 each** (661 existing + 34 new); no failures, skips or errors |
| PostgreSQL-only tests (9 files, including the concurrency tests) | 5 further runs, **91 of 91 each** |
| Frontend unit tests | **70 of 70** (6 new, covering the planning arithmetic) |
| Frontend type check, lint and production build | All pass |
| Frontend API types | Identical to the running API (115 paths) |
| Browser tests, Stage 6 screens | **51 of 51**, no page errors |
| Browser regression of earlier stages on the Stage 6 code | Stock 55/55, kitchen issues 48/48, stock counts 57/57, meal records 54/54 |
| Migration on the temporary server | 17/17 (empty), 44/44 (copy); API on the copy 26/26 |
| Read-only checks of the running development API (port 8000) | Planning 40/40; meal records 26/26; stock counts 27/27; kitchen issues 24/24; stock 23/23; purchasing 54/54 |

### What the Stage 6 browser tests cover

- classifying an item and the new Kind column;
- copying a menu into drafts and approving a standard;
- creating a plan:
  - with the AT05 figures, immediate recalculation, rounding up to whole
    pieces and the stock gap;
  - with an override refused without a reason, then saved, approved and
    frozen;
  - with no stock movement as a result;
- cancelling and replacing an approved plan;
- the same-named meal-session warning;
- planned versus actual on the meal record;
- a suggested standard (48.78 g per person) saved as a draft;
- phone-width layout on all six new screens;
- Staff with older permissions seeing no planning and being refused by
  the server;
- another campus being unable to see the plans.

### A note on one earlier run

One full backend run had 694 passed and 1 failed.

- **Cause:** the development laptop went to sleep on battery for about
  35 minutes during that run, from 09:05 to 09:40 (system power log). The
  test's 30-minute sign-in token expired between two of its requests.
- **Not a code fault:** the same test passes on its own.
- **What was done:** the later runs kept the laptop awake. No test and no
  part of sign-in or security was changed to get a pass.

---

## 6. Permissions and Staff-grant verification

- **Who can plan:** Admins and Kitchen Managers only. Every planning
  screen and server endpoint checks both the role and the permission.
- **Staff:** the new planning permissions cannot be assigned to Staff.
  A Staff user is refused even if a planning permission were written
  directly into the database.
- **Item kind:** only Admins and Kitchen Managers can classify an item.
  A Staff user with an older "inventory update" permission (for example
  the existing Staff account #3) cannot, and their normal item editing
  works as before.
- **Approvals:** approving standards and plans, and cancelling an
  approved plan, are Admin and Kitchen Manager actions. Approving one's
  own draft is allowed for now (interim; client question Q3).
- **Campus isolation:** users of one campus cannot see or change another
  campus's standards or plans (tested).
- **Staff grants unchanged:**
  - account #3's 23 permission grants and all 26 Staff grants are
    identical before and after the change, checked by content
    fingerprint;
  - no grant refers to the new planning permissions;
  - no permission was granted, changed or deactivated.

---

## 7. Requirement traceability

Full criteria and evidence are in `REQUIREMENTS-TRACEABILITY.md`
(section 5, "Stage 6 — meal planning").

| ID | Requirement (proposal) | Status | Evidence in brief |
|---|---|---|---|
| PLAN01 | Create a meal plan from date, session, menu and expected headcount; only the main items needed | **TESTED** | Plan form and API; any subset of main items; browser and backend tests |
| PLAN02 | Per-person standards; raw or prepared items; different menus, different standards; weight and count | **TESTED** | Versioned standards, item kind, g/kg/pc units with explicit conversions |
| PLAN03 | Suggest standards from history (used ÷ served), reviewed and approved before use | **TESTED** | Suggestion preview with exclusions; saved as a draft with its basis; 48.78 g example |
| PLAN04 | Required = headcount × standard; immediate recalculation; g→kg; round up pieces; keep original figures in saved plans | **TESTED** | AT05 figures; 226 pieces; frozen at approval; database triggers |
| PLAN05 | Additional quantity = max(0, required − available); current availability labelled | **TESTED** | Gap shown per item (rice 67.5 kg needed, 30 kg in stock, 37.5 kg to buy) |
| PLAN06 | One-day overrides with a reason; effective-dated standards; older plans unchanged; audit history | **TESTED** | Override rules; versions; full history |
| PLAN07 | Planning never changes stock | **TESTED** | Stock and purchasing tables compared before and after on SQLite, PostgreSQL, the development-data copy and in the browser |
| PLAN08 | Compare planned and actual results | **IN_PROGRESS** | Built for meals cooked in-house; received quantities for outsourced food wait for Stage 8 |
| MEAL02 | Prepared dishes linked to ingredient issues; planned vs actual usage | **TESTED** | Criterion 4 completed: planned versus actual on the meal record |
| AT05 | Biryani for 450: rice 150 g → 67.5 kg, chicken 200 g → 90 kg; recalculates; no stock movement | **TESTED** | Automated test and browser walkthrough |
| AT06 | New plans use the updated standard; older plans keep theirs; traceable | **TESTED** | Automated test (version 2 used by new plans; approved plan keeps version 1); history |

---

## 8. Interim rules and outstanding client decisions

The rules below were built so planning can be used now. **They are not
client decisions.** Each will be replaced or confirmed when the client
answers. No client decision has been assumed.

| Open question | What it covers | Interim rule built |
|---|---|---|
| Q3 (proposal §17.2) | Who approves new portion standards and menus | Admins and Kitchen Managers (the roles in the approved permission matrix); approving one's own draft is allowed |
| Client questions §5.2 | Who can change ingredient standards | Admins and Kitchen Managers, as in the permission matrix |
| Client questions §5.3 | Can the same menu have different standards on different days | Dated versions plus one-day overrides; no weekday-specific standards |
| Q7, Q8 | Units, item-specific conversions, weight-to-piece | Explicit conversion records only; weight-to-piece never assumed |
| Q2 | Who may edit master data | Item kind: Admins and Kitchen Managers only; other item fields unchanged |
| C5 | Four or five meal sessions; duplicate "Breakfast"/"breakfast" on campus 1 | Sessions used exactly as stored; a same-named session is reported, never linked |
| Client questions §5.1 | How the daily headcount is collected | Expected headcount typed in, or taken from the meal record of the same session |
| Proposal §4.2 | Historical corrections | Approved plans: cancel with a reason and create a new plan. Approved standards: approve a newer version |
| Permission matrix | Who creates meal plans (the matrix lists only approval) | Admins and Kitchen Managers |
| Q11 | Retained leftovers carried into another meal | Carried food is shown apart from prepared output in comparisons (the Stage 5 interim process) |

### Points for the client to confirm

1. Who should approve portion standards and meal plans, and whether the
   person who prepared a plan may also approve it.
2. Whether a menu needs different quantities on particular days, beyond
   dated versions and one-day overrides.
3. The units and item-specific conversions used in the kitchen, and
   whether any weight-to-piece conversion is approved.
4. Whether the campus uses four or five meal sessions, so the duplicate
   "Breakfast"/"breakfast" sessions can be cleaned up.
5. How the daily headcount is collected.
6. Who may create meal plans.

---

## 9. Dependencies

| Dependency | Effect on Stage 6 | Status |
|---|---|---|
| **Stage 8 — outsourced food** (OUT01–OUT03, AT04) | PLAN08 criterion 3 ("prepared or received food quantities") is met only for prepared food. Received quantities for outsourced meals need the outsourced-food records. Outsourced items cannot yet be planned | Not started; PLAN08 stays IN_PROGRESS |
| **PUR05 — supplier returns, and STK01's supplier-return part** | The stock gap uses current stock balances. Supplier returns do not yet post to the stock ledger, so balances do not reflect goods returned to suppliers until PUR05 is built | Blocked by client question Q6 (supplier credits, rejected deliveries and returns) |
| Earlier stages (3, 4, 5) | Planning reads stock balances (Stage 4) and closed meal records with their actual usage (Stage 5). It does not depend on purchase orders, and no purchase order is created from a plan | In place and re-tested (section 5) |

---

## 10. TESTED versus ACCEPTED

The project uses these statuses (`REQUIREMENTS-TRACEABILITY.md`,
section 9):

- **TESTED** — built and verified by automated tests, browser tests and
  checks on the development system, with the evidence recorded.
- **ACCEPTED** — the client has reviewed the delivered requirement and
  confirmed it. Only the client can give this status.

Every Stage 6 requirement above is at most **TESTED**. None is ACCEPTED.
Approving the Stage 6 plan, and the 5 November 2026 approval of the
proposal and permission matrix, are not acceptance of these requirements.

### Suggested client review

1. **AT05 walkthrough:** plan a biryani for 450 people with rice at 150 g
   and chicken at 200 g per person. Confirm 67.5 kg and 90 kg, the
   recalculation when the headcount changes, and that no stock moves.
2. **AT06 walkthrough:** approve a new version of a standard. Confirm
   that new plans use it and an older approved plan keeps its original
   figures, with the change visible in the history.
3. **Review the interim rules** in section 8 and answer the points listed
   there.
4. **Confirm the screens:** Portion Standards, Meal Plans, item
   classification and the planned-versus-actual panel on meal records.

When the client confirms a requirement, its status can be changed to
ACCEPTED in the traceability matrix, with the date and who confirmed it.

---

## 11. Notes and known limitations

- The existing "menu main items" are kept unchanged and are not used by
  planning. Their quantities can be copied into draft standards, each of
  which needs approval.
- Campus 1 still has both "Breakfast" and "breakfast" meal sessions.
  Planning reports this and never links across them; the clean-up waits
  for client question C5.
- No item is classified yet. An Admin or Kitchen Manager needs to classify
  items as raw or prepared before their standards can be approved.
- No portion standards or meal plans exist in the development data yet.
  The figures in this report come from the test data and the temporary
  copy described in section 4.2.
- The stock gap shows today's stock; it does not forecast deliveries or
  quantities on order.

---

## 12. Change summary and repository state

| Area | Files |
|---|---|
| Backend (12) | New: planning routes, planning models, migration `f3a8c2d61b47`, two test files. Changed: permission set, master-data routes (item kind refused in item forms; units, items and conversions used by planning are protected), meal-record routes (planning panel), application wiring, model registration, item model, one existing test file |
| Frontend (23) | New: Portion Standards and Meal Plans screens (six pages), planning components, the item-classification action, planning helpers and arithmetic with unit tests. Changed: navigation, route permissions, endpoints, the shared resource page (value labels, notice, row action), items and menu-main-items pages, meal-record page and types, generated API types |
| Documentation (5 plus this report) | `STAGE-6-PLANNING-PLAN.md` (with an as-built section), `REQUIREMENTS-TRACEABILITY.md`, `REMAINING-WORK.md`, `diagrams/ERD.md`, `DEVELOPMENT-SAFETY.md`, and this report |

**Repository state:**

- All Stage 6 work is in the working tree and **has not been committed,
  pushed or deployed**.
- The development database is at `f3a8c2d61b47`.
- No environment file, protected file or Staff permission grant was
  changed.

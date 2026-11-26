# Stage 5 — Meal Management (MEAL01–MEAL05): Implementation Plan

Prepared 23 November 2026, after Stage 4 (slices 4a–4c) was built and
applied (development database at `0e7d99065bd3`); revised the same day
for permissions, retained leftovers and reopening. This is a plan, not
evidence; statuses stay in `REQUIREMENTS-TRACEABILITY.md`. The decisions
in section 4 were **approved on 23 November 2026**, with closing by
`meal.update` and reopening by ADMIN and KITCHEN_MANAGER only; Stage 5 was
built and migration `ea00e5387c2f` (M5) applied the same day (section 8).
Interim rules stay interim until the client answers (section 6).

Every rule below is marked as one of:
- **Project decision** — yours to approve; the proposal does not settle it
  and it is not a client business rule.
- **Interim — Client Qn** — what is built while a client question is open.
  It is not the client's answer, is labelled as interim in the
  application's documentation, and is replaced when the client answers.

Sources: `PROPOSAL.md` §4.2 (permission matrix), §5.3 (MEAL01–MEAL05), §6
(daily workflow), §9.5, §11.1, §17.2 (Q6, Q11); `client-notes.md` §5;
`CLIENT-QUESTIONS.md` §5; `BACKEND-COMPLETION-PLAN.md` (C5, M5, D10);
`STAGE-4-STOCK-PLAN.md` (S5: the meal-record link of STK02);
`diagrams/ERD.md`.

**Numbering.** `REMAINING-WORK.md` lists meals as stage 7 and master-data
gaps as stage 5. This plan is the meals stage you asked for as "Stage 5"
(MEAL01–MEAL05, plus the STK02 meal-record link left open by S5). It does
not include the master-data stage (item kind, meal-session clean-up),
except where a decision below says how meals work without it.

## 1. What exists today

- `meal_sessions` (campus 1: Breakfast, Lunch, Evening Snack, Dinner,
  plus "early morning" and a duplicate "breakfast"; campus 2: four) and
  `menus` (each in one meal session; the data holds day menus such as
  "Monday Lunch", not single dishes), with `menu_main_items` (per-person
  ingredient standards).
- `daily_headcounts`: one student count per campus per date (182 rows of
  seeded data), read by the dashboard only; no entry screen or API.
- Kitchen issues and unused returns (Stage 4) carry date, meal session and
  menu, with issued, returned and net quantities per item.
- Waste tracking records prepared-food waste (`PREPARED_FOOD`, free-text
  food name, optional menu and meal session); it never changes stock.
- Items are raw ingredients; there is no "prepared" or "outsourced" item
  kind yet (master-data gap, migration M3).
- Permission codes: `headcount.*` (STAFF-assignable, used only by the
  dashboard), `consumption.*` (kitchen issues), `menu.*`,
  `outsourced_food.*` (unused). STAFF user #3 holds all of these.

## 2. Approved rules this plan follows (no decision needed)

- MEAL01–MEAL05 acceptance criteria as written in `PROPOSAL.md` §5.3,
  including: expected and actual counts stay separate; people counts and
  food quantities are never interchangeable; available = distributed +
  remaining; leftover classifications reconcile with the remaining
  quantity; nothing is counted twice; retained food is never a purchase;
  invalid quantities are refused with a clear message.
- Campus isolation and backend authorization on every endpoint; audit
  rows for every change (§4.3, §13).
- Prepared food never moves raw-ingredient stock: the stock formula
  (§5.2) has no prepared-food term; raw usage is the kitchen issues.
- The four approved roles and the Stage 3/4 permission boundaries stay as
  they are; no existing STAFF grant changes.

## 3. Open client questions that affect this stage

None of these is answered. The interim behaviour built meanwhile is in
section 4 and is not to be recorded as a client decision.

| Ref | Question | What is built meanwhile |
|---|---|---|
| **Q11** | Approved process for retained leftovers carried into another meal or day (also `CLIENT-QUESTIONS.md` §5.4: should leftovers be carried forward?) | 5-5: retained food may be carried once, whole, as its own dish line; no reprocessing, partial carry, time limit or approval step |
| **CQ §5.1** | How daily student headcount is collected | 5-2: counts entered by hand; no attendance link (Won't-have §11.4) |
| **C5** | Four or five meal sessions; the duplicate "Breakfast"/"breakfast" and "early morning" on campus 1; sessions have no order or time | Records use the sessions as stored; "later meal" means a later date or another session of the same date (5-5) |
| **Q6** | Supplier credits, returns and payables | 5-6: "returned to supplier" is a leftover classification only |
| **Q3** / planning | Approved standards and meal plans (PLAN01–08) | 5-8: the planned side of MEAL02 criterion 4 waits for planning |
| **§4.2 note** | Permissions for historical corrections "will be defined before implementation" | 5-9: reopening by ADMIN and KITCHEN_MANAGER with a reason |
| **Matrix gap** | The approved matrix assigns no meal-record duties to the Store Keeper or Accounts and does not say who may close or reopen a meal record | 5-1: meal codes assignable to STAFF by an Admin, none granted; closing and reopening as in 5-1 and 5-9 |

## 4. Decisions needed before building

| # | Decision | Recommendation | Kind |
|---|---|---|---|
| **5-1** | Who may view, record, close and reopen meal records | New module `meal`: `meal.read`, `meal.create`, `meal.update`, added to the KITCHEN_MANAGER set and the STAFF-assignable list; no grant inserted, no existing grant or role changed. Full matrix in 4.1: `meal.update` edits **OPEN** records only; a CLOSED record is read-only for everyone; **closing** needs `meal.update`; **reopening** is ADMIN and KITCHEN_MANAGER only, by role. Every rule is enforced by the API (and the database where it can be) and mirrored in the screens | Project decision; interim for the matrix gap (Client) |
| **5-2** | Meal record and headcounts (MEAL01) | One record per campus, date and meal session. Expected students, staff and guests as three whole numbers (≥ 0); actual people served as the same three groups, separate fields, entered on or after the meal date. Expected counts up to 14 days ahead. `daily_headcounts` and the dashboard unchanged. The date and meal session are fixed once the record exists (4.4) | Project decision; 14-day window and group-level actuals interim — Client CQ §5.1 |
| **5-3** | What a prepared dish is (MEAL02) | A dish line: free-text name, optional menu of that session, output quantity > 0, one campus unit (weight, volume or count) | Project decision (until the master-data stage adds prepared-food items) |
| **5-4** | Distribution, leftovers, reconciliation (MEAL03–05) | Per dish, in that dish's unit, no conversions: available (output, or the carried quantity for a carried-in line), distributed, remaining; available = distributed + remaining (API and database). Leftovers split the remaining quantity into RETAINED, RETURNED_TO_SUPPLIER, WASTED, DISPOSED lines, each with quantity and remarks. Closing requires exact reconciliation of every dish and the actual counts | Project decision implementing the approved MEAL criteria |
| **5-5** | Retained leftovers (MEAL04 criterion 3) | Rules in 4.2: only a RETAINED line of a CLOSED record can be carried; it is carried **once** (database unique constraint), **whole**, into an OPEN later record of the same campus, where it becomes its **own dish line with the same name and unit** (not merged into another dish, no unit conversion); source meal, dish, leftover, quantity and unit are stored on it and the source line is locked. Never a stock movement, purchase, receipt, supplier return, credit or payment | **Interim — Client Q11** |
| **5-6** | Wasted and returned-to-supplier leftovers | Recorded on the meal record only: no waste record is created (waste tracking unchanged; its screen warns not to enter meal leftovers again); no supplier return, credit or payable change | Project decision; returned-to-supplier interim — Client Q6 |
| **5-7** | Linking ingredient issues (MEAL02 criterion 3; STK02 criterion 4) | Derived from campus, date and meal session; no change to Stage 4 tables or behaviour; treatment during corrections in 4.4 | Project decision |
| **5-8** | Planned vs actual usage (MEAL02 criterion 4) | Actual net usage now; planned side with the planning stage; MEAL02 stays IN_PROGRESS; no interim calculation from `menu_main_items` | Project decision; planned side waits for Client Q3 / planning |
| **5-9** | Correcting a recorded meal | Statuses OPEN, CLOSED, CANCELLED (4.3). Closing per 5-1; reopening by ADMIN or KITCHEN_MANAGER with a reason; who reopened, when and why kept on the record and in the audit history, with every later change and closure (4.3) | **Interim — §4.2 historical corrections (Client)** |
| **5-10** | Migration M5 | One additive migration: `meal_records`, `meal_dishes`, `meal_leftovers` (carry-forward link on the dish line) and the `meal` permission rows; no existing table or row changes; Stage 4 procedure (throwaway round trip, full PostgreSQL suite, verified backup, snapshots, smoke tests) | Project decision |

### 4.1 Permissions (5-1, 5-9)

| Action | ADMIN | KITCHEN_MANAGER | STAFF with the code | STAFF without |
|---|---|---|---|---|
| View meal records and lists | Yes | Yes | `meal.read` | No |
| Create a meal record (with expected counts) | Yes | Yes | `meal.create` | No |
| Edit an OPEN record: counts, dishes, distribution, leftovers, carry retained food in, remove a carried-in line | Yes | Yes | `meal.update` | No |
| Edit a CLOSED record | No — reopen first | No — reopen first | No | No |
| Close an OPEN record (only when fully reconciled) | Yes | Yes | `meal.update` | No |
| Cancel an OPEN record (no carried links) | Yes | Yes | `meal.update` | No |
| Reopen a CLOSED record (reason required) | Yes | Yes | **Never**, whatever codes are held | Never |
| See the record's change history | Yes | Yes | No (`audit.read` is never STAFF-assignable) | No |

- Closing by `meal.update` is recommended because closing is gated by
  exact reconciliation and only an ADMIN or KITCHEN_MANAGER can undo it.
  Alternative if you prefer a review step: closing by ADMIN and
  KITCHEN_MANAGER only.
- **Backend:** every endpoint checks campus, the permission code or role
  and the record's status; a CLOSED or CANCELLED record refuses every
  change (409) except reopening by role (403 for anyone else). The database
  keeps the status fields consistent (check constraints) and the status
  change itself is made under a row lock, so a change racing a close is
  refused.
- **Frontend:** route guards (`meal.read` for the list and detail,
  `meal.create` for a new record); edit, close and cancel controls only on
  OPEN records for users with `meal.update`; Reopen only for ADMIN and
  KITCHEN_MANAGER on CLOSED records; the history panel only for ADMIN and
  KITCHEN_MANAGER. The screens never replace the API checks.
- **Tests:** API refusals for each action and role (including STAFF with
  every meal code trying to reopen, and edits to CLOSED records), another
  campus, and browser checks that each control appears only where allowed.

### 4.2 Retained leftovers — interim until Client Q11 (5-5)

- **Source:** a RETAINED leftover line on a CLOSED meal record. Lines of an
  OPEN record cannot be carried (their quantities may still change).
- **Destination:** an OPEN meal record of the same campus, other than the
  source, dated on or after the source date. Sessions have no order (C5),
  so another session on the same date counts as later.
- **What carrying creates:** a carried-in dish line on the destination
  with the source dish's name and unit and the retained quantity as its
  available quantity (output 0). It is distributed and classified like any
  dish, so food not served again is accounted for on the destination.
- **Same dish, same unit:** yes, in the interim. Carried food keeps its name
  and unit; it is not added into another dish and not converted. Whether
  retained food may be reprocessed into a different dish is part of Q11.
- **Whole quantity only:** the retained quantity is carried in full; any
  part not used is classified on the destination (for example as wasted).
- **Never twice:** the carried-in line stores the source leftover id under
  a database unique constraint, and the carry is made under a lock on the
  source line; a second carry is refused, also when two users try at once.
- **References kept:** the carried-in line stores the source meal record,
  source dish line and source leftover line (foreign keys) and copies the
  name, quantity and unit at carrying time.
- **Source locked:** while carried, the source leftover line cannot be
  edited, reclassified or deleted, even if its record is reopened. To change
  it, the carried-in line is first removed from its destination (only while
  that destination is OPEN), which frees the source line again.
- **Uncarried retained food** stays listed as open retained food; there is
  no expiry or automatic disposal (Q11).
- **No inventory or money effect:** carrying, and every other meal action,
  creates no stock movement, purchase, receipt, supplier return, credit or
  payment; tests check those tables are unchanged.
- **Not built until Q11 is answered:** partial carry, reprocessing into
  another dish, time limits, approval of a carry, carrying between campuses.

### 4.3 Status, closing, reopening and audit history — interim until the §4.2 corrections rule (5-9)

- **Statuses:** OPEN (editable), CLOSED (reconciled, read-only), CANCELLED
  (an OPEN record created for the wrong date or session, with no carried
  links; kept with its reason; frees the date and session for a new
  record). There is no delete.
- **On the record:** status; closed by and at (latest); reopened by, at and
  reason (latest), and the number of times reopened; cancelled by, at and
  reason. Database checks keep each status with its fields.
- **Audit history** (the existing audit log, one row per action, never
  updated or deleted by the application): creation; every change, with the
  values before and after; each closing, with a snapshot of the counts,
  dishes, distribution, leftovers, carried links and the linked issues
  with net usage per item; each reopening (who, when, reason); each
  cancellation. A record reopened several times keeps every cycle. The
  audit log has no database-level protection today; adding a trigger like
  the stock ledger's would be a separate approval.
- **After reopening:** changes are allowed as for an OPEN record and
  audited the same way; closing again requires reconciliation again and
  stores a new closing snapshot; earlier snapshots stay.

### 4.4 Linked ingredient issues during corrections (5-7)

- The meal record never creates, changes or reverses a kitchen issue or
  return and never posts stock. Issues are corrected only in the kitchen
  issue module, by its Stage 4 rules (reversal and re-entry, ADMIN and
  KITCHEN_MANAGER) and its own permissions; nothing in Stage 4 changes.
- The link is the record's campus, date and meal session, so the date and
  session cannot be edited after creation; a record made for the wrong
  ones is cancelled (while OPEN and with no carried links) and recorded
  again.
- Linked issues and net usage are shown live. A closing snapshot stores
  them. If an issue for that date and session is confirmed, reversed or
  returned after closing, Stage 4 is not blocked; the meal record shows
  "issues changed since closing" with the difference per item. An ADMIN or
  KITCHEN_MANAGER may reopen and close it again to record a new snapshot.

## 5. Design (after approval)

- **API** (campus-scoped): meal records list (date range, session, status),
  create, detail (counts, dishes, distribution, leftovers, carried-in and
  carried-out retained food, linked issues and net usage, changes since
  closing), update while OPEN, close, cancel, reopen (ADMIN/KM, reason),
  history (ADMIN/KM); open retained food available for carrying; form
  options for users without `menu.read` (sessions, menus, units).
- **Screens:** Meals under Operations: list with status and date filters;
  meal record page in workflow order (headcounts; dishes and output;
  distribution and leftovers with a live reconciliation check; carried
  retained food; linked issues and net usage; history for ADMIN/KM); phone
  layout.
- **Tests:** one per MEAL criterion on SQLite and PostgreSQL; races (two
  records for one session, close racing an edit, closing twice, carrying
  one retained line twice); every rule in 4.1–4.4; permission matrix for
  ADMIN, KITCHEN_MANAGER, STAFF with and without each code, another
  campus; no stock, purchase, return or payment rows created; browser
  checks at desktop and phone width; Stage 3/4 regression (full suite,
  Stage 4 browser suites, smoke tests).

## 6. Still requiring client clarification

These stay open whatever is approved here; the interim behaviour is
replaced when the client answers.

1. **Q11** — the retained-leftover process: whether retained food may be
   carried at all, how long, into which meals, whether it may be
   reprocessed into another dish or carried in part, and who authorises it.
2. **CQ §5.1** — how and when headcounts are collected; whether actual
   people served are counted per group (students, staff, guests) or only
   as a total; how far ahead expected counts are entered.
3. **Matrix gap** — whether Store Keepers or other kitchen staff record
   meal data, and who closes and reopens meal records.
4. **§4.2 historical corrections** — the permanent rule for correcting a
   closed meal record.
5. **C5** — the meal sessions (four or five, the campus 1 duplicates) and
   their order within a day.
6. **Q6** — what "returned to supplier" means for credits and balances.
7. **Q3 / planning** — approved standards, needed for the planned side of
   MEAL02.

## 7. Estimate

About 6.5–7.5 developer-days including migration, screens, tests and
documentation (half a day more than first estimated, for the carry-forward
locks, cancellation and the audit history panel). MEAL01, MEAL03, MEAL04
and MEAL05 can become TESTED; MEAL04 criterion 3 is met for the interim
process only until Q11 is answered; MEAL02 stays IN_PROGRESS (planned
side, 5-8); STK02 can become TESTED once 5-7 is built and tested.

## 8. As built (23 November 2026)

Built to sections 4.1–4.4 and decisions 5-1 to 5-10; evidence and statuses
in `REQUIREMENTS-TRACEABILITY.md` section 3.

Choices made while building, within the approved decisions (for your
review; none is a client decision):

| Choice | Why |
|---|---|
| One leftover line per classification per dish (database unique) | A remaining quantity can then be split once per class; nothing is counted twice |
| Leftovers may stay unclassified while the record is OPEN; when entered they must add up exactly to the remaining quantity | Staff record distribution first and classify later; closing requires it |
| A dish's output and unit change only before its distribution is recorded (clear the distribution first) | The distribution was reconciled against the old output |
| The net usage per item at each closing is stored on the record (and in the audit row) | Needed to show "issues changed since closing" |
| Expected and actual totals shown; no per-person usage | Planned-versus-actual waits for planning (5-8) |
| A STAFF user with `meal.create` but not `meal.read` gets a "Record a Meal" menu entry and stays on the form after saving | They may record but not view meals |
| Meal records are locked `FOR NO KEY UPDATE`, in id order when a carry touches two records | Serialises changes without blocking foreign-key checks; no deadlock between crossing carries |
| The waste screen's description says meal leftovers must not be entered again | 5-6 |
| Test fixtures: the SQLite test database switches foreign-key checks off before dropping tables | Dishes and leftovers reference each other once food is carried |

Interim rules built, still waiting for the client (section 6): the
retained-leftover process (Q11), the 14-day window and per-group actual
counts (headcount collection), meal recording by STAFF through assignable
codes (matrix gap), reopening as the correction route (§4.2),
"returned to supplier" without credits (Q6), sessions as stored (C5).

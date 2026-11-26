# Stage 6 — Meal Planning (PLAN01–PLAN08, AT05, AT06): Implementation Plan

Prepared 24 November 2026, after Stage 5 was built and applied (development
database at `ea00e5387c2f`). Decisions 6-1 to 6-9 were **approved on
24 November 2026**, with the 6-8 clarification and the safeguards in
section 5; the section 12 choices and the migration name M4 were approved
the same day. **Built on 24 November 2026; migration `f3a8c2d61b47` (M4)
applied to the development database the same day** (section 17). This is a
plan, not evidence; statuses and evidence are in
`REQUIREMENTS-TRACEABILITY.md`. Nothing is ACCEPTED.

Every rule below is marked as one of:
- **Approved requirement** — stated in `PROPOSAL.md` or the approved
  permission matrix (05 November 2026).
- **Project decision** — approved by you (6-1 to 6-9, safeguards S6-1 to
  S6-6); not a client business rule.
- **Interim — Client Qn** — what is built while a client question is open.
  It is not the client's answer, is labelled interim in the documentation,
  and is replaced when the client answers.

Sources: `PROPOSAL.md` §4.2 (permission matrix), §5.5 (PLAN01–PLAN08), §5.7
(master data, item kind), §6 (daily workflow), §9.2 (units), §14 (AT05,
AT06), §17.2 (Q2, Q3, Q7, Q8); `CLIENT-QUESTIONS.md` §5;
`client-notes.md` §5; `BACKEND-COMPLETION-PLAN.md` (C5, M3, M4);
`STAGE-4-STOCK-PLAN.md`; `STAGE-5-MEAL-PLAN.md` (5-8); ADR-006, ADR-007;
`diagrams/ERD.md`.

## 1. Scope and numbering

- **Stage 6 = `REMAINING-WORK.md` row 6 (planning)**: PLAN01–PLAN08, AT05,
  AT06, and MEAL02 criterion 4 (planned side, left open by Stage 5
  decision 5-8).
- **Plus one master-data item from row 5**: the item kind (raw, prepared,
  outsourced), which PLAN02 criterion 2 needs (6-1).
- **Not in this stage** (6-1): search-as-you-type, meal-session clean-up
  (C5), supplier returns (row 4, Q6), outsourced food (row 8), reports and
  exports (row 9), the AI plan-and-procure job (row 12).
- **Migration name.** The migration bundle for planning in
  `BACKEND-COMPLETION-PLAN.md` is **M4** (the item-kind column comes from
  bundle M3). The 23 November proposal message called it "M6"; M6 is the
  outsourced-food bundle, so this plan uses **M4**.

## 2. What exists today (read-only queries, 24 November 2026)

- **Menus and menu main items:** 21 menus (campus 1: 13; campus 2: 8) and
  48 menu main items (24 per campus). Each holds a quantity per person, all
  by weight and in the item's base unit. They are edited in place through
  the master-data screens (`menu.create`, `menu.update`) with no versions.
- **Items:** 123 items (base units: kg 88, L 28, pc 7), with no item kind.
- **Unit conversions:** both campuses have explicit records g↔kg, ml↔L and
  identity records (9 per campus). There is no weight↔piece record.
- **Meal sessions:** campus 1 has six, including "Breakfast", "breakfast"
  and "early morning" (C5); campus 2 has four.
- **Meal records:** none yet (Stage 5 tables are empty).
- **Older STAFF grants:** STAFF #3 holds older, active, non-assignable
  grants that include `menu.create`, `menu.update`, `inventory.create` and
  `inventory.update`. These stay unchanged. Section 6 explains why planning
  does not use those codes.

## 3. Approved requirements this plan follows

| Rule | Source |
|---|---|
| A plan has a date, meal session, menu and expected headcount; only the main items needed are selected; entering every ingredient is not compulsory | PLAN01 |
| Standards are per person, per selected item; items are identified as raw or prepared; different menus may use different standards for the same item; weight- and count-based quantities | PLAN02 |
| Suggested standard = total quantity used ÷ total people served, over historical records the user selects, in compatible units; shown for review; a responsible user approves it before it applies | PLAN03 |
| Required quantity = expected headcount × approved quantity per person; recalculated immediately when headcount or standard changes; gram-to-kilogram display; count-based quantities rounded up to whole pieces; saved plans keep the standard and quantity used | PLAN04 |
| Additional procurement = max(0, required − available stock); available stock labelled as current availability, not a forecast | PLAN05 |
| One-day overrides need a reason and apply only to the selected plan; standards have effective dates; older plans keep their values; changes audited | PLAN06 |
| Creating or editing a plan never changes stock; only confirmed receipts, issues, returns and approved adjustments do | PLAN07 |
| Compare planned vs actual ingredient usage, headcounts, prepared or received quantities, distributed and leftover quantities | PLAN08 |
| Manage portion standards: Admin and Kitchen Manager. Approve meal plans and standards: Admin and Kitchen Manager. Store Keeper and Accounts: neither | Permission matrix §4.2 |
| Conversions only through explicit `unit_conversions` records; weight-to-piece is never assumed | §9.2, ADR-007 |
| 450 people × 150 g rice = 67.5 kg; × 200 g chicken = 90 kg; recalculates on headcount change; no stock movement | AT05 |
| New plans use the updated standard; older saved plans keep their original standard and quantity; changes traceable | AT06 |

## 4. Approved decisions (24 November 2026)

| # | Decision | Approved rule | Kind |
|---|---|---|---|
| **6-1** | Scope | Planning plus item kind only (section 1) | Project decision |
| **6-2** | Standards vs menu main items | New versioned `portion_standards` table. The 48 menu main items are not changed. "Copy into draft standards" creates **drafts only**; an Admin or Kitchen Manager approves each one; nothing is approved automatically. The menu-main-items screen keeps working, labelled "not used by planning" | Project decision |
| **6-3** | STAFF assignability | None of the new codes is STAFF-assignable in Stage 6. `STAFF_ASSIGNABLE_PERMISSIONS` is unchanged | Project decision |
| **6-4** | Who creates plans | ADMIN and KITCHEN_MANAGER | Interim — matrix gap (the matrix lists approval only; the user story names the Kitchen Manager) |
| **6-5** | Approval | ADMIN and KITCHEN_MANAGER, by role. Approving one's own plan or standard is allowed (the matrix requires an independent approver only for stock adjustments) | Interim — Client Q3 |
| **6-6** | Recalculation vs history | A plan uses the standard version in effect on its date. A DRAFT plan recalculates on every change of headcount, selection, override or standard. An APPROVED plan is frozen. A correction = cancel the approved plan with a reason and create a new plan. No reopening | Project decision; correction route interim — proposal §4.2 historical corrections |
| **6-7** | Headcount and dates | One expected total per plan. Pre-filled from the expected counts (students + staff + guests) of the meal record for the **same** campus, date and meal session, when one exists (S6-1). The comparison shows both. One live plan per campus, date and meal session. Plans are created for today or later | Project decision; headcount entry interim — Client CQ §5.1 |
| **6-8** | Item kind (as clarified) | **Only ADMIN and KITCHEN_MANAGER may set or change `item_kind`**, enforced by role in the backend and reflected in the frontend. An `inventory.create` or `inventory.update` grant (including STAFF #3's older grants) never permits classification. No grant is changed. A standard can be approved only for a classified item. OUTSOURCED items cannot be planned until the outsourced-food stage | Project decision; who edits master data interim — Client Q2 |
| **6-9** | PLAN08 status | Built for in-house meals. Received (outsourced) quantities come with Stage 8, so PLAN08 stays IN_PROGRESS until then | Project decision |

## 5. Approved safeguards and how each is enforced

| # | Safeguard | Backend (API) | Database | Frontend | Tests |
|---|---|---|---|---|---|
| **S6-1** | Ambiguous meal-session matching is reported, never silently linked | Plans and meal records are linked only by exact campus, date and `meal_session_id`. If a live record or plan exists on that date in a **different** session with the same name (ignoring letter case and extra spaces, e.g. "Breakfast" / "breakfast"), the response carries a warning naming it, and nothing links to it or pre-fills from it. A plan's menu must belong to the plan's exact session | One live plan per campus, date and session (partial unique index); no foreign key or name-based link between plans and meal records | Warning banner on plan create, plan detail, comparison and the meal record page; never a link to the similar-named record | Duplicate-session cases on SQLite and PostgreSQL: exact match links; similar-only match is reported and not linked; both present links the exact one and reports the other |
| **S6-2** | Approved standards and plans are immutable | Every edit of an APPROVED or CANCELLED standard, or of an APPROVED or CANCELLED plan and its lines, is refused. The only change to an approved plan is APPROVED → CANCELLED with a reason (6-6). A wrong approved standard is corrected by approving a newer version (section 9) | Triggers: `portion_standards` and `portion_standard_basis` refuse UPDATE and DELETE once the standard is not DRAFT; `meal_plans` allows only APPROVED → CANCELLED (cancel fields only) and nothing on CANCELLED; `meal_plan_lines` refuse INSERT, UPDATE and DELETE unless the plan is DRAFT; approval refused unless every line has its snapshot | No edit controls on approved or cancelled records | API refusals on SQLite and PostgreSQL; direct SQL UPDATE and DELETE refused on PostgreSQL |
| **S6-3** | Explicit approved conversion records only | A standard's unit must be the item's base unit or have an explicit `unit_conversions` record to it; otherwise refused. Gap and kg/L display use only explicit records; no weight↔piece conversion is ever derived. If a record later becomes unavailable, the screen shows "no approved conversion" and no gap | Unit, item and conversion references from the new tables are added to the existing "in use" checks, so a conversion used by a standard or plan is frozen and a used unit or item cannot be deleted (existing master-data rules, extended to the new tables) | Unit choices limited to convertible units | Refusal without a record; weight→piece refused; AT05 kg display through the g→kg record |
| **S6-4** | No automatic approval of copied standards | Copy creates DRAFT rows only, marked `COPIED`. Approval is a separate call by ADMIN or KITCHEN_MANAGER per standard. Drafts are never used by plans | Status check; approved rows require `approved_by` and `approved_at` | Copied drafts shown as "Draft — needs approval" | Copy produces drafts only; a plan cannot use a draft; STAFF and unapproved paths cannot approve |
| **S6-5** | Plans never create or modify stock movements, purchase orders, receipts or supplier transactions | The planning code writes only planning tables, audit rows, and `items.item_kind` through the classification action. Stock is read only for the current balance | Stage 4 append-only triggers unchanged | Planning screens have no stock, order, receipt or supplier actions | Every planning endpoint run with fingerprints of `stock_movements`, kitchen issues and returns, stock counts and adjustments, `purchase_orders` and lines, `purchases` and items, goods receipts and lines, `supplier_payments` and `supplier_returns` and lines, unchanged before and after (SQLite and PostgreSQL); a static test that the planning modules import none of those models for writing |
| **S6-6** | Interim rules and open client questions documented | Interim rules named in code comments where enforced | — | The plan and standards screens' help text names interim rules | This file (sections 4, 9, 11); traceability, ERD, remaining-work and safety documents updated when built |

## 6. Permissions

- **New modules and codes (M4):** `portion_standard` (`portion_standard.read`,
  `.create`, `.update`) and `meal_plan` (`meal_plan.read`, `.create`,
  `.update`). Added to the KITCHEN_MANAGER set in `dependencies.py`. Not
  STAFF-assignable (6-3). **No grant is inserted, changed or deactivated.**
- **Why not `menu.*` or `inventory.*`:** STAFF #3 holds older active
  `menu.create`, `menu.update`, `inventory.create` and `inventory.update`
  grants. Reusing those codes would let a STAFF user manage standards or
  classify items, which the matrix does not allow.
- **By role, not by code:** approving standards and plans, cancelling an
  approved plan, and setting `item_kind` are ADMIN and KITCHEN_MANAGER only
  (same pattern as meal reopening).
- **Effective access:**

| Action | ADMIN | KITCHEN_MANAGER | STAFF (any grants) | Other campus |
|---|---|---|---|---|
| View standards / plans | Yes | Yes | No | 404 |
| Create and edit drafts; copy from menu; suggestions | Yes | Yes | No | 404 |
| Approve a standard or plan | Yes | Yes | No | 404 |
| Cancel a draft | Yes | Yes | No | 404 |
| Cancel an approved plan (reason) | Yes | Yes | No | 404 |
| Set or change `item_kind` | Yes | Yes | **No, even with `inventory.update`** | 404 |
| Plan vs actual on the meal record page | Yes | Yes | No (needs `meal_plan.read`) | 404 |

- **Item kind enforcement (6-8):** classification only through a dedicated
  action (`PUT /api/items/{id}/kind`, role check, audited with before and
  after values). The existing item create and update endpoints refuse an
  `item_kind` field from anyone, so no `inventory.*` grant can classify.
  Item lists and details return the kind to anyone who can read items. The
  item screen shows the kind as an editable field only to ADMIN and
  KITCHEN_MANAGER; STAFF see it read-only. STAFF users' existing item edits
  (name, category and so on, through older grants) keep working as today.

## 7. Database changes — one additive migration (M4)

Additive only. No existing row is changed except `alembic_version` and the
inserted module and permission rows.

- **`items.item_kind`**: nullable text, check `RAW`, `PREPARED` or
  `OUTSOURCED`. Existing 123 items stay NULL ("Not classified"); no
  backfill.
- **`portion_standards`**: `campus_id`, `menu_id`, `item_id`,
  `quantity_per_person` (> 0, same precision as menu main items), `unit_id`,
  `effective_from` (date), `version_no` (per campus, menu and item),
  `status` (`DRAFT`, `APPROVED`, `CANCELLED`), `source` (`MANUAL`, `COPIED`,
  `SUGGESTED`), `copied_from_menu_main_item_id` (plain reference, no foreign
  key, so deleting a menu main item keeps working as today), `item_kind`
  (copied at approval), notes, created / approved / cancelled by and at,
  cancel reason.
  Checks: status and source values; APPROVED requires approver, time and
  item kind; CANCELLED requires a reason. Unique `(campus_id, menu_id,
  item_id, version_no)`.
- **`portion_standard_basis`** (PLAN03 traceability): `standard_id`,
  `meal_record_id`, quantity used and people served copied at the time of
  the suggestion. Unique `(standard_id, meal_record_id)`.
- **`meal_plans`**: `campus_id`, `plan_seq` and `plan_number` (`MP-00001`
  per campus, through the existing `next_number`), `plan_date`,
  `meal_session_id`, `menu_id`, `expected_headcount` (whole number ≥ 1),
  `status` (`DRAFT`, `APPROVED`, `CANCELLED`), notes, created / updated /
  approved / cancelled by and at, cancel reason. Partial unique index: one
  non-cancelled plan per campus, date and meal session. Checks as for
  standards.
- **`meal_plan_lines`**: `plan_id`, `campus_id`, `item_id`, `standard_id`,
  optional `override_quantity_per_person` with `override_reason` (both or
  neither; reason not blank), and the snapshot written at approval:
  item kind, standard quantity and unit, quantity per person used, required
  quantity (standard unit, rounded up for count units), the item's base
  unit, the conversion factor used and the required quantity in the base
  unit. Unique `(plan_id, item_id)`.
- **Triggers** (S6-2): as in section 5. The Stage 4 `stock_movements`
  triggers are not touched.
- **Modules and permissions**: 2 module rows, 6 permission rows. No grants.
- **Audit entity types**: `PORTION_STANDARD`, `MEAL_PLAN`; item-kind changes
  use the existing item audit entries.
- **Not touched**: `menu_main_items` (48 rows), `daily_headcounts`, every
  Stage 3, 4 and 5 table, every existing grant.
- **Downgrade**: refuses while any meal plan, portion standard, classified
  item or grant on the new codes exists (same pattern as M5).

## 8. Calculations

- **Standard in effect for a plan dated D:** the APPROVED versions for the
  menu and item with `effective_from ≤ D`; the latest `effective_from`
  wins, then the highest `version_no`.
- **Required quantity (standard unit)** = expected headcount × (override if
  present, else the standard's quantity per person). Exact decimals. For a
  count unit (`pc`), rounded **up** to a whole number.
- **Display:** weights also shown in kg and volumes in L, only through the
  campus's explicit g→kg and ml→L records (AT05: 67,500 g shown as
  67.5 kg).
- **Gap (item base unit)** = max(0, required × explicit factor to the base
  unit − current balance from the Stage 4 balance query). Labelled
  "Current availability (today's balance), not a forecast". Quantities on
  order are not counted.
- **Suggestion (PLAN03)**: for the closed meal records the user selects,
  the total net usage of the item (from each record's closing snapshot, in
  the item's base unit) ÷ total actual people served (students + staff +
  guests). Records that are not CLOSED, are cancelled, have no actual counts,
  have zero people served or never used the item are listed as excluded,
  with the reason. The result is shown unrounded, then saved as a DRAFT in
  the unit the user picks (explicit conversion), rounded to the column
  precision, with its basis records.
- **Plan vs actual (PLAN08, MEAL02 criterion 4)** for a plan and the meal
  record of the same campus, date and session (S6-1):
  - per item: planned required (base unit) vs actual net usage, difference,
    planned vs actual per person;
  - items used but not planned are listed too;
  - headcounts: plan expected total, the meal record's expected total, and
    its actual total;
  - prepared output, carried retained food shown separately (not counted as
    prepared — Interim, Q11), distributed, and leftovers by
    classification;
  - an open meal record is marked "not closed; figures may change".

## 9. Workflows

- **Standards**:
  - DRAFT → APPROVED: ADMIN or KITCHEN_MANAGER. Item classified and not
    OUTSOURCED; menu and item active; unit convertible (S6-3); effective
    date today or later.
  - DRAFT → CANCELLED: needs a reason.
  - APPROVED is final. A newer approved version (later date, or the same
    date with a higher version) supersedes it for plans dated on or after
    its effective date. Superseded versions are shown as history.
- **Plans**:
  - DRAFT → APPROVED: ADMIN or KITCHEN_MANAGER. At least one line; every
    line has a standard in effect on the plan date; plan date today or
    later. Approval writes the snapshot and freezes the plan.
  - DRAFT → CANCELLED: needs a reason. A draft whose date has passed can
    only be cancelled.
  - APPROVED → CANCELLED: ADMIN or KITCHEN_MANAGER, needs a reason. Frees
    the slot for a replacement plan (6-6).
- **Concurrency**: plan and standard changes lock their row
  (`FOR NO KEY UPDATE`); version numbers are taken under a key-share lock
  on the menu row, backed by the unique index; plan numbers through
  `next_number`; a second live plan for the same slot → 409.
- **Audit**: every create, edit, copy, suggestion save, approval,
  cancellation and item-kind change is an audit row in the same
  transaction, with before and after values.

## 10. API and screens (sketch)

- `/api/portion-standards`: list and detail with version history
  (`portion_standard.read`); create draft, copy from a menu, save a
  suggestion (`.create`); edit or cancel a draft (`.update`); suggestion
  preview; `POST /{id}/approve` (role).
- `/api/meal-plans`: form options and create (`meal_plan.create`); list,
  detail with live figures for drafts, and comparison (`.read`); edit draft
  headcount, lines and overrides; cancel a draft (`.update`);
  `POST /{id}/approve` and cancel of an approved plan (role).
- `PUT /api/items/{id}/kind` (role).
- `GET /api/meal-records/{id}` gains the linked plan and comparison, and the
  S6-1 warning, for users with `meal_plan.read`.
- **Screens**: Planning section in the sidebar (Meal plans, Portion
  standards); standards list per menu with history, draft form, copy and
  suggest; plan list, new plan and plan detail with immediate
  recalculation; comparison panel on the plan and on the meal record page;
  item kind on the items screen; the "not used by planning" label on the
  menu-main-items screen (6-2). Phone width (390 px) supported.

## 11. Client questions still open — interim rules built

| Question | Interim rule in Stage 6 |
|---|---|
| **Q3** / CQ §5.2 — who approves and changes standards and menus | ADMIN and KITCHEN_MANAGER (matrix roles); self-approval allowed (6-5) |
| **CQ §5.3** — different standards on different days for the same menu | Effective-dated versions plus one-day overrides; no weekday-specific standards |
| **Q7 / Q8** — units, item-specific and weight-to-piece conversions | Explicit records only; no weight↔piece (S6-3) |
| **Q2** — who edits master data | Item kind: ADMIN and KITCHEN_MANAGER only (6-8); other item fields unchanged |
| **C5** — four or five meal sessions; duplicates on campus 1 | Sessions used as stored; similar names reported, never linked (S6-1) |
| **CQ §5.1** — headcount collection | Expected total typed in or pre-filled from the exact meal record (6-7) |
| **§4.2** — historical corrections | Approved plans: cancel and replace (6-6); approved standards: superseded by a newer version |
| **Matrix gap** — who creates meal plans | ADMIN and KITCHEN_MANAGER (6-4) |
| **Q11** — retained leftovers (Stage 5 interim) | Carried food shown separately from prepared output in comparisons |
| **Outsourced (§6 of client questions)** | OUTSOURCED items not plannable; PLAN08 received quantities wait for Stage 8 (6-9) |

## 12. Implementation choices within the approved decisions

These follow from the decisions and safeguards above. They are listed so
they can be corrected before building:

1. **Correcting an approved standard (S6-2):** never edited; a newer
   version is approved. At the same effective date, the higher version
   wins.
2. **No back-dating:** a standard's effective date must be today or later
   when it is approved.
3. **Similar session names (S6-1):** same name ignoring letter case and
   extra spaces only; no other fuzzy matching.
4. **Item kind (6-8):** set only through the dedicated action; can be
   changed between the three values but not cleared; approved standards and
   plan lines keep the kind they used.
5. **Expected headcount:** a whole number of at least 1.
6. **Past-dated drafts:** can only be cancelled.
7. **Copied standards:** keep a plain reference to the source menu main
   item (no foreign key), so deleting a menu main item works as today.

## 13. Slices, order and estimate (one developer)

| Slice | Content | Requirements | Days |
|---|---|---|---|
| **6a** | Migration M4 (written once for all slices, verified on throwaway databases, applied once at the end); item kind with role enforcement; versioned standards: draft, approve, cancel, history, copy to draft, audit | PLAN02, PLAN06 (versions) | 3–3.5 |
| **6b** | Meal plans: create, main-item selection, immediate recalculation, count rounding, kg/L display, overrides with a reason, gap, approve, cancel, snapshot, S6-1 warnings | PLAN01, PLAN04, PLAN05, PLAN06 (overrides), PLAN07, AT05, AT06 | 4–4.5 |
| **6c** | Suggestions from closed meal records; plan vs actual on the plan and the meal record page | PLAN03, PLAN08, MEAL02 criterion 4 | 2.5–3 |
| — | Migration procedure, full verification, documentation | — | 1 |
| | **Total** | | **10.5–12** |

## 14. Verification plan

- **Migration (procedure S7 of `DEVELOPMENT-SAFETY.md`):** throwaway
  PostgreSQL 16 round trip (upgrade, downgrade, re-upgrade) on an empty
  database and on a restored copy of the development data; downgrade guard;
  API on the copy; full PostgreSQL suite; `pg_dump -Fc` backup with
  read-back; read-only snapshot, apply one revision, snapshot: only
  `alembic_version`, `modules` and `permissions` written; content
  fingerprints of every existing table identical; STAFF grant fingerprints
  unchanged (user #3: 23 rows; all STAFF: 26 rows); Stage 4 triggers
  unchanged; new triggers present.
- **Backend tests (SQLite and PostgreSQL):** AT05 exactly (67.5 kg, 90 kg,
  recalculation, no stock row); AT06 (new version used by new plans; the
  older approved plan unchanged; audit trail); formulas, rounding and
  display; gap with explicit conversions only; every safeguard S6-1 to S6-5
  as in section 5; item kind refused for STAFF with `inventory.update` and
  for the generic item endpoints; four-role and other-campus checks on every
  endpoint; concurrency (simultaneous approve and cancel, two plans for one
  slot, version numbering); database triggers on PostgreSQL only.
- **Full suites:** full PostgreSQL suite twice; PostgreSQL-only files five
  times; SQLite suites.
- **Frontend:** unit tests for the planning calculations; type check, lint,
  production build; generated API types equal to the live API.
- **Browser:** Stage 6 scenarios for ADMIN, KITCHEN_MANAGER, STAFF with
  older grants, STAFF without codes, other campus and phone width; Stage 4
  (4a, 4b, 4c) and Stage 5 browser suites against the Stage 6 code.
- **Development API smoke tests (read-only):** planning, meals, counts,
  kitchen, stock, Stage 3.

## 15. Expected statuses when built and tested

- **TESTED:** PLAN01–PLAN07, AT05, AT06, MEAL02 (criterion 4 met).
- **IN_PROGRESS:** PLAN08 (received outsourced quantities, Stage 8 — 6-9).
- **ACCEPTED:** nothing without explicit client acceptance.

## 16. Implementation boundaries

- Nothing is built until you say to start.
- No other stage is started (no outsourced food, reports, master-data
  clean-up or AI work).
- No grant is inserted, changed or deactivated; `STAFF_ASSIGNABLE_PERMISSIONS`
  is unchanged; permission and module rows only through M4.
- Menu main items, meal sessions, `daily_headcounts` and all Stage 3, 4 and
  5 data are not modified. The only change to an existing screen's
  behaviour is the label on the menu-main-items screen (6-2) and the item
  kind field (6-8).
- Plans never create or change stock movements, purchase orders, receipts
  or supplier transactions (S6-5); no purchase order is created from a plan.
- No backfill of item kind; no automatic approval of anything.
- Protected files, `.env`, the Homebrew database on port 5432 and other
  containers are not touched. `AGENT_ENABLED` stays `False`.
- No commit, push or deploy.

## 17. As built (24 November 2026)

- **Migration M4 `f3a8c2d61b47`** (revises `ea00e5387c2f`): `items.item_kind`
  with `ck_item_kind`; `portion_standards`, `portion_standard_basis`,
  `meal_plans`, `meal_plan_lines` with the checks and indexes of section 7;
  the four triggers of S6-2 (`portion_standards_final`,
  `portion_standard_basis_final`, `meal_plans_final`,
  `meal_plan_lines_final`); modules `portion_standard` and `meal_plan` with
  six permission rows; no grant. 44 tables, 164 foreign keys after it.
- **Backend:** `app/models/planning.py`, `app/api/routes/planning.py`
  (`/api/portion-standards`, `/api/meal-plans`, `PUT /api/items/{id}/kind`);
  changes to `dependencies.py` (Kitchen Manager set; planning codes noted as
  never STAFF-assignable), `master_data.py` (item forms refuse `item_kind`;
  units, items and conversions used by standards and plan lines count as
  in use), `meals.py` (planning panel on the meal record), `main.py`,
  `models/__init__.py`, `models/master_data.py`.
- **Frontend:** Menu Planning → Portion Standards (list, detail, new draft,
  copy from menu, suggest from past meals) and Meal Plans (list, new plan,
  plan detail with editing, approval, cancellation, plan versus actual and
  history); the planning panel on the meal record page; the Kind column
  and Classify action on Items (ADMIN and KITCHEN_MANAGER only); the "Not
  used by planning" notice on Menu Main Items; both planning routes
  limited to ADMIN and KITCHEN_MANAGER.

Choices made while building (within the approved decisions):

- A draft standard has no version number; the next version number is
  given at approval, so "the higher version wins" means "approved later"
  (section 12, choice 1).
- Approving a plan writes and flushes the line snapshots before the plan's
  status changes, because the lines trigger allows changes only while the
  plan is a draft.
- The plan's figures are shown in the unit of its standard or override,
  also in kg (from g) or L (from ml) when an explicit record exists, and in
  the item's stock unit for the gap.
- Draft plans with a past date show the reason they cannot be approved;
  they can only be cancelled (section 12, choice 6).
- Copying a menu takes a key-share lock on the menu row so two copies at
  once cannot create the same draft twice; a menu main item already copied
  into a pending draft is skipped with the reason.
- On the meal record page the planning panel is shown only to ADMIN and
  KITCHEN_MANAGER (`meal_plan.read`); STAFF who may read meal records see
  the record as before.

Still open with the client (unchanged from section 11): Q3, client
questions §5.1–§5.3, Q7/Q8, Q2, C5, §4.2 historical corrections, the
matrix gap for who creates plans, Q11 (carried food in comparisons) and the
outsourced-food questions (PLAN08 received quantities).

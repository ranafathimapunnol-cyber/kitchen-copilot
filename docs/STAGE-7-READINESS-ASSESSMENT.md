# Kitchen Copilot — Stage 7 Implementation Readiness Assessment

## Master data completion (`REMAINING-WORK.md` row 5)

| | |
|---|---|
| Prepared | 24 November 2026, after Stage 6 (development database at `f3a8c2d61b47`) |
| Type | Assessment only. Nothing is implemented. No code, database row, migration, permission, grant or environment file was changed |
| Scope confirmation | "Stage 7" = the master-data gaps of `REMAINING-WORK.md` row 5, confirmed on 24 November 2026 |
| Sources | `REMAINING-WORK.md`; `PROPOSAL.md` §4.2, §5.7, §9.2, §9.5, §11.4, §17.2; `STAGE-6-COMPLETION-REPORT.md`; `REQUIREMENTS-TRACEABILITY.md`; `BACKEND-COMPLETION-PLAN.md` (C1–C8, M3, D10); `CLIENT-QUESTIONS.md`; `client-notes.md`; `STAGE-5-MEAL-PLAN.md`; `STAGE-6-PLANNING-PLAN.md`; `diagrams/ERD.md`; the backend routes, models and migrations and the frontend forms named below; read-only queries of the development database on 24 November 2026 |

**A note on numbering.**
- Older documents use "Stage 7" for meal records (`REMAINING-WORK.md` row 7,
  `STAGE-4-STOCK-PLAN.md`); those were delivered as "Stage 5".
- "Stage 8" means outsourced food (row 8).
- This assessment uses **Stage 7 = master-data completion**, as confirmed.

**Labels used here.** Every rule and decision below is marked as one of:
- **Approved requirement** — stated in `PROPOSAL.md` or the approved
  permission matrix.
- **Client decision needed** — an open client question.
- **Project decision needed** — yours to approve before building.
- **Interim rule (existing)** — already applied in earlier stages, not a
  client decision.

The **S7-A to S7-H** labels name pieces of work in this assessment only.
They are not requirement IDs.

---

## 1. Scope and requirement references

### 1.1 There are no master-data requirement IDs

The SRD and the proposal give master data no requirement IDs. §5.7 is
narrative, and the traceability matrix has no master-data rows.

This assessment does not invent IDs. Scope is traced to these sources:

| Source | Text | Where it stands |
|---|---|---|
| `PROPOSAL.md` §5.7 | "Search-as-you-type selection lists will be provided for frequently used items and suppliers." | **Not built.** Every item and supplier picker is a plain dropdown (section 2.2) |
| `PROPOSAL.md` §5.7 | Each item has a name, category, kind (raw, prepared or outsourced), standard unit, minimum stock and active status | Built; the item kind was added in Stage 6 (decision 6-8) |
| `PROPOSAL.md` §5.7 | Configurable master data: campuses, categories, units, conversions, items, suppliers, meal sessions, menus, menu main items, portion standards | Built, except campuses (no API; row 11, organisation administration) |
| `PROPOSAL.md` MEAL01 | Meal records for "breakfast, lunch, snacks and dinner" | Sessions are free text; campus 1 also has "breakfast" and "early morning" (C5) |
| `PROPOSAL.md` §9.2 | "Weight-to-piece conversion must never be assumed. It requires an approved item-specific conversion." | Conversions are campus-wide unit pairs; item-specific conversions are not modelled (Q8) |
| `PROPOSAL.md` §17.2 Q2 | "Who may create or edit each master-data type?" | Open |
| `BACKEND-COMPLETION-PLAN.md` C5, M3 | Four or five meal sessions; "five canonical meal sessions via a session code" (ERD §8) | Open |
| `BACKEND-COMPLETION-PLAN.md` C6 | Expiry flags and lots (ERD §8) versus the proposal's **Won't have** "Expiry and batch tracking" | Proposal excludes it |
| `BACKEND-COMPLETION-PLAN.md` C8 | Supplier screen versus navigation for Kitchen Managers (protected file) | Open, needs approval to change the protected file |
| `REQUIREMENTS-TRACEABILITY.md`, MEAL02 note | "Dish names are free text until the master-data stage adds prepared-food items" | Not built |
| `REMAINING-WORK.md` row 5 | Search-as-you-type; duplicate meal-session clean-up; C5; Q2 | Item kind and portion standards were done in Stage 6 |

### 1.2 Proposed scope

| Label | Work | Basis | Can start now? |
|---|---|---|---|
| **S7-A** | Search-as-you-type for items and suppliers in every entry form and filter that picks one (section 2.2) | Approved requirement (§5.7) | **Yes**: no client decision, no migration, no permission change |
| **S7-B** | Meal sessions: resolve the "Breakfast"/"breakfast" duplicate and "early morning" on campus 1; optional canonical session codes and display order | C5 (client) | **No**: blocked by C5 |
| **S7-C** | Who may create or edit each master-data type, and representing it in permission codes | Q2 (client); matrix §4.2 | **Partly**: the matrix already answers the main roles (section 7); a code split needs Q2 and approval |

### 1.3 Candidates that need an explicit decision before inclusion

| Label | Work | Why it is only a candidate |
|---|---|---|
| **S7-D** | Prepared-food items: let a meal dish optionally name a PREPARED item instead of free text | Noted in MEAL02 evidence; changes a Stage 5 table (additive). Project decision |
| **S7-E** | Item-specific conversions, e.g. pieces to grams for one item | §9.2; blocked by client questions Q7 and Q8 (approved conversions). Touches every conversion lookup (bills, receipts, issues, counts, planning) |
| **S7-F** | Case-insensitive name uniqueness (meal sessions, possibly items, suppliers, menus) | Prevents another "Breakfast"/"breakfast". Project decision; the meal-session index cannot be added until S7-B removes the duplicate |
| **S7-G** | Let Kitchen Managers see suppliers read-only (C8) | Needs approval to edit the protected `apps/web/src/app/dashboard/suppliers/page.tsx` |
| **S7-H** | Data quality: menus with placeholder-looking names on campus 1 ("vnsjdnv" active; "fjasnf", "f4fr" inactive; "egg", "egg banana" on "early morning") | Only the client or Admin can say whether they are real. Project data; no change without confirmation |

### 1.4 Out of scope

- Expiry and lot tracking (C6): the proposal lists it as Won't have.
- Campuses, organisations and SUPER_ADMIN: row 11, migration M1, which
  needs its own authorisation.
- A role-permissions table and new actions: M8, row 11.
- Supplier returns (row 4: PUR05, blocked by Q6).
- Outsourced food (Stage 8).
- Reports and exports (row 9).
- Importing historical master data (Q12, Q13).

---

## 2. What is already implemented and reusable

### 2.1 Backend

- **Generic master-data routes** (`app/api/routes/master_data.py`) for
  categories, units, conversions, items, suppliers, meal sessions, menus
  and menu main items:
  - create, edit, deactivate, and ADMIN-only delete;
  - an audit row for every change;
  - campus isolation;
  - "historical integrity" checks (`find_unit_references`,
    `find_item_references`, `unit_pair_is_used`) that stop a unit's
    dimension, an item's stock unit or a used conversion from changing.
    These are reusable for any merge or deactivation in S7-B.
- **Item kind and its role-only setter** (`PUT /api/items/{id}/kind`,
  Stage 6). The item forms refuse the field.
- **Same-name detection** (`normal_name`, `similar_sessions` in
  `app/api/routes/planning.py`, Stage 6): finds meal sessions whose names
  match ignoring letter case and extra spaces. Reusable for an S7-B
  duplicate report and for S7-F.
- **Name search patterns:** `like_contains` with escaped `%` and `_` in
  `stock.py` and `purchase_orders.py`, used by the stock balances, the item
  ledger and the purchase-order list.
- **Explicit conversion handling:**
  - `get_unit_conversion_factor` (`master_data.py`);
  - `converted` (`kitchen.py`);
  - the `Units` helper (`planning.py`).
  Any S7-E change starts from these three.
- **Form option endpoints** that return the lists each form may use under
  its own permission (meal records, kitchen issues, standards, plans).

### 2.2 Frontend

- `ResourcePage` (master-data screens) already searches loaded records on
  the page. `SearchInput` exists, and the stock-count sheet filters items
  as you type.
- Item and supplier pickers that are plain dropdowns today (S7-A):

| Form | Picks |
|---|---|
| New supplier bill | supplier; item per line |
| Purchase order form | supplier; item per line |
| Kitchen issue form | item per line |
| Opening stock | item |
| Waste tracking | item |
| Record payment | supplier |
| Portion standard form, suggestion page | item |
| Stock movements, supplier payments (filters) | item, supplier |

- Each form already loads its complete list from the endpoint it uses
  today (e.g. `fetchAllRecords(ENDPOINTS.items)`, supplier balances). A
  search-as-you-type list can filter what is already loaded, so S7-A needs
  **no new endpoint and no permission change**.

### 2.3 Development data (read-only queries, 24 November 2026)

- **Lists are small:** items 63 (campus 1) and 60 (campus 2); suppliers 8
  each; two items inactive.
- **Meal sessions on campus 1:** Breakfast (#1), Lunch (#2), Evening Snack
  (#3), Dinner (#4), "early morning" (#9) and "breakfast" (#10). Campus 2
  has the four standard sessions.
- **Duplicates:** "breakfast" (#10) is the only case-only duplicate name
  in any master-data table (items, suppliers, categories, units, menus,
  meal sessions). The unique constraint `uq_meal_session_campus` is
  case-sensitive, so it allowed the duplicate.
- **What uses the duplicate sessions today:** only menus — "breakfast"
  has 1 (inactive), "early morning" has 3 (one inactive). No kitchen
  issue, waste record, meal record or meal plan uses any campus 1 session
  yet. A clean-up now is cheap; once kitchen issues, meal records and
  plans use these sessions, every clean-up option means changing or
  re-linking more records.

---

## 3. Dependencies on Stages 3–6

| Stage | How Stage 7 touches it | Impact |
|---|---|---|
| 3 — purchase orders and bills | S7-A replaces the supplier and item dropdowns in the order and bill forms | Regression of the order and bill flows (create, edit draft, bill against order) |
| 4 — stock ledger, issues, counts | S7-A in opening stock, kitchen issues and the stock-movement filter. Kitchen issues reference meal sessions, so S7-B must not re-link issues without approval. The append-only ledger is unaffected: no master-data change ever rewrites a movement | Regression of the 4a, 4b and 4c browser suites; ledger triggers unchanged |
| 5 — meal records | Meal records reference meal sessions (one live record per campus, date and session); S7-D would add an optional item link to dishes | A session merge would collide with that rule once records exist. S7-D changes a Stage 5 table |
| 6 — planning | Standards, plans and the S6-1 same-name warnings depend on session identity. S7-A applies to the standard form and the suggestion page. Plans link to meal records only on the exact `meal_session_id` | After S7-B the S6-1 warnings should no longer fire on campus 1. The exact-id rule stays. Frozen units and conversions (S6-3) also limit S7-E |

---

## 4. Open client questions that affect Stage 7

| Question | Affects | Status |
|---|---|---|
| **C5** — four or five meal sessions; what to do with "breakfast" and "early morning" on campus 1 | S7-B, S7-F | Open (`BACKEND-COMPLETION-PLAN.md` C5; the D10 default "four sessions" was a recommendation, not a recorded decision) |
| **Q2** (§17.2) — who may create or edit each master-data type | S7-C | Open; the matrix (§4.2) answers it for the four roles at the level of "manage" |
| **Q7** (§17.2), client questions §3.3 — units used for each item | S7-E | Open |
| **Q8** (§17.2) — approved weight-to-piece conversions | S7-E | Open |
| **C8** — Kitchen Managers' supplier screen | S7-G | Project-side; needs approval to edit the protected file |
| **Q12, Q13** — historical data import and who validates it | Seeding master data | Open; out of scope |
| **C1, C3** — role model; mapping Store Keeper and Accounts duties onto STAFF codes | S7-C | Open (`BACKEND-COMPLETION-PLAN.md`) |

---

## 5. Client decisions, existing interim rules and project decisions

### 5.1 Already approved — no decision needed

- **Search-as-you-type** for items and suppliers (§5.7).
- **Permission matrix** (§4.2, 5 November 2026):
  - categories, units, items and menus: Admin and Kitchen Manager;
  - suppliers: Admin and Accounts (Kitchen Managers read-only, decision of
    17 November 2026).
- **Explicit conversions only;** weight-to-piece never assumed (§9.2,
  ADR-007).
- **Item kind** set only by Admin and Kitchen Manager (decision 6-8).

### 5.2 Existing interim rules (kept until the client answers)

- **Meal sessions are used exactly as stored** (C5; Stage 5, 5-2;
  Stage 6, S6-1). Same-named sessions are reported, never linked.
- **Who edits master data** (Q2): as the matrix and the current codes
  allow, with the older STAFF grants kept unchanged (section 7).
- **No item-specific conversions** (Q7, Q8): campus-wide explicit pairs
  only.

### 5.3 Client decisions needed

1. **C5:** four or five meal sessions. Is "early morning" a real session?
   Should "breakfast" (#10) be the same as "Breakfast" (#1), and should its
   inactive menu "fjasnf" move or stay?
2. **Q2:** who may add or edit items, categories, units, conversions,
   menus and suppliers — in particular whether Store Keepers may add
   items, and whether Accounts manage suppliers without touching items.
3. **Q7 and Q8** (only if S7-E is wanted): the units and item-specific
   conversions the kitchen uses.
4. **S7-H:** whether the placeholder-looking menus are real.

### 5.4 Project decisions needed (yours)

| # | Decision | Recommendation |
|---|---|---|
| P7-1 | Scope: S7-A now; S7-B and S7-C after C5 and Q2; which candidates (S7-D to S7-H) to include | Start S7-A; decide the candidates separately |
| P7-2 | Search approach | Filter the lists each form already loads, in the browser: one shared, accessible search-select component. No new endpoint or permission. Revisit server-side search only if lists exceed a few hundred per campus |
| P7-3 | Clean-up mechanism once C5 is answered | Choose per the answer: rename, deactivate (deactivation has no undo screen today), or merge (moves references; needs explicit approval because it changes existing rows). Prefer doing it before operations use these sessions |
| P7-4 | Canonical session codes | Add `meal_sessions.code` only if the client confirms the session list; nullable, not backfilled by the migration (the item-kind approach of Stage 6) |
| P7-5 | Case-insensitive uniqueness (S7-F) | Add for meal sessions after S7-B; items and suppliers have no duplicates today, so they could be added now if wanted |
| P7-6 | Permission codes for master data versus receipts (S7-C) | Do not split codes in Stage 7 unless Q2 requires it. A split is a permission-structure change, like the Stage 3 `purchase_bill.*` split, and older STAFF grants would need a separately approved mapping |

---

## 6. Database and migration impact

| Work | Migration | Existing data |
|---|---|---|
| S7-A search-as-you-type | **None** | None |
| S7-B session codes / order (if approved) | **M3** (additive): `meal_sessions.code` nullable with a check on the approved list; partial unique `(campus_id, code)`; optionally `sort_order` | None by the migration. Codes are set afterwards by an Admin, or by an explicitly approved data step |
| S7-B duplicate clean-up | Usually none (rename or deactivate through the existing screens) | **Changes existing rows.** Needs explicit approval and the full backup procedure. A merge would update `menus.meal_session_id` (and any later issues, meal records or plans) |
| S7-F case-insensitive uniqueness | M3: unique index on `(campus_id, lower(name))` | The meal-session index fails until the duplicate is resolved; items and suppliers are clean today |
| S7-C code split (only if Q2 requires) | Permission rows (like `a3c9e1f47b20`) | Older STAFF grants: mapping needs its own approval |
| S7-D prepared-food items | `meal_dishes.item_id` nullable FK to `items` (PREPARED) | None |
| S7-E item-specific conversions | New table, or `unit_conversions.item_id`, plus lookup changes | None, but it changes how future quantities convert |

**Procedure:** any migration follows the S7 procedure in
`DEVELOPMENT-SAFETY.md`:
- a throwaway round trip on an empty database and on a copy of the
  development data;
- the full PostgreSQL suite twice;
- a verified backup;
- exactly one revision applied, with read-only snapshots before and after;
- code sync and read-only smoke tests.

Long runs go under `caffeinate -i`.

**Protections that must stay unchanged:**
- the stock-ledger triggers;
- the four Stage 6 planning triggers;
- every STAFF grant.

---

## 7. Permissions and roles

The approved matrix has four roles: Admin, Kitchen Manager, Store Keeper
and Accounts. The code has `ADMIN`, `KITCHEN_MANAGER` and `STAFF`. Store
Keeper and Accounts duties are given to STAFF users one permission code at
a time (C1 and C3 open). The target platform role `SUPER_ADMIN` is not
built (row 11).

| Role (matrix) | In code | Master data today | Stage 7 implication |
|---|---|---|---|
| **Admin** | `ADMIN` | Everything, including permanent delete and item kind | Performs any approved session clean-up; can set session codes if S7-B is approved |
| **Kitchen Manager** | `KITCHEN_MANAGER` (fixed code set) | Categories, units, conversions, items, menus, meal sessions, menu main items, item kind; suppliers read-only by API (decision 17 Nov 2026) | Matrix "Yes" for categories, units, items and menus is met. The suppliers link opens a screen that is ADMIN-only (C8, protected file, S7-G) |
| **Store Keeper** | `STAFF` with assigned codes | `inventory.read` and `menu.read` are assignable; `inventory.create/update` and `menu.create/update` are **not** | Matrix: Store Keepers do **not** manage items, categories, units or menus, but **do** record receipts. Receipts use `inventory.create/update`, the same codes as master-data writes, so the role cannot be granted receipts without master-data writes. This is why those codes are not assignable. Resolving it needs Q2 and a code split (P7-6) |
| **Accounts** | `STAFF` with assigned codes | No supplier-only code exists; supplier writes use `inventory.*` | Matrix: Accounts manage suppliers, not items. Not representable without a code split (P7-6) |
| *(target)* SUPER_ADMIN | not built | — | No master-data role inside campuses in the target design. Out of scope |

**Older STAFF grants.** STAFF user #3 still holds active, non-assignable
older grants: `inventory.create`, `inventory.update`, `menu.create`,
`menu.update` and others.
- They let that user create and edit items, categories, units, suppliers,
  menus and meal sessions, which the matrix gives only to Admins and
  Kitchen Managers.
- The standing rule keeps these grants unchanged, and Stage 7 must not
  change them.
- The conflict is documented here for the client's Q2 answer.
- Stage 6 already prevents these grants from setting item kind or
  touching planning.

**S7-A changes no permission.** The search filters lists each form already
loads under its own permission. Server-side search, if ever chosen, must
stay inside each module's option endpoint and keep that module's check
(as the meal and planning option endpoints do), never a general item
lookup open to every role.

---

## 8. Test requirements

### 8.1 Backend

- **S7-A:** none, unless server-side search is chosen (then:
  case-insensitive partial match, escaped `%` and `_`, active-only option,
  limits, campus isolation, each module's permission).
- **S7-B:**
  - migration round trip (empty and copy), constraint tests, downgrade
    guard;
  - the clean-up itself tested on the copy first;
  - every reference (menus, issues, waste, meal records, plans) checked
    before and after;
  - the S6-1 warning no longer firing for resolved sessions;
  - audit rows.
- **S7-C:** a role and permission matrix test per master-data type for
  Admin, Kitchen Manager, STAFF with and without the older grants, and
  another campus; STAFF grants identical before and after.
- **S7-D to S7-F, if included:** additive-migration tests and reference
  checks. S7-E also needs conversion tests across bills, receipts,
  issues, counts and planning.

### 8.2 Frontend

- Unit tests (`node --test`) for the search-select filtering logic:
  - case and whitespace handling;
  - matching inside names;
  - inactive items shown only where a form allows them;
  - keyboard selection logic in a pure helper.
- TypeScript, ESLint and production build.
- Generated API types regenerated and compared if any endpoint changes.

### 8.3 Browser (headless, scratch stack)

- Each form in section 2.2 with the new picker: type, pick, keyboard-only
  use, clear, validation on an empty pick, and 390 px phone width.
- STAFF with older grants and STAFF without codes see only what they can
  today.

### 8.4 Regression

- Full PostgreSQL suite twice and the nine PostgreSQL-only files five
  times.
- Browser suites:
  - stock 4a, kitchen 4b, counts 4c;
  - meals (Stage 5) and planning (Stage 6);
  - purchase order and bill flows.
- Read-only smoke tests on port 8000 after any sync.

---

## 9. Risks, blockers and implementation sequence

### 9.1 Blockers

| Blocks | Waiting for |
|---|---|
| S7-B meal-session clean-up and codes | **C5** |
| S7-C code split | **Q2**, plus approval of any change to permission rows and of a mapping for older STAFF grants |
| S7-E item-specific conversions | **Q7, Q8** |
| S7-G supplier screen for Kitchen Managers | Approval to edit the protected file |
| Nothing blocks S7-A | — |

### 9.2 Risks

| Risk | Mitigation |
|---|---|
| The duplicate sessions become expensive to clean once operations use them (today only menus reference them) | Ask the client for C5 now; do S7-B before kitchen issues, meal records and plans are recorded against campus 1 sessions |
| S7-A touches about ten forms across Stages 3–6 | One shared component; per-form browser checks; full regression suites |
| Accessible search-select behaviour (keyboard, screen readers, phone) | Follow the combobox pattern; keyboard-only browser checks; phone width |
| Older STAFF grants contradict the matrix for master data | Documented only; no grant change without approval (section 7) |
| A merge would change existing rows | Requires explicit approval, backup and the full procedure; prefer rename or deactivate where the answer allows |
| SQLite and PostgreSQL differ on case-insensitive matching | If server-side search or S7-F are built, test both databases |
| Long test runs stalled by the laptop sleeping | Run under `caffeinate -i` (`DEVELOPMENT-SAFETY.md`) |

### 9.3 Recommended sequence

1. **7a — search-as-you-type (S7-A).**
   - Shared search-select component with unit-tested filtering.
   - Roll out to the forms in section 2.2.
   - Browser and regression tests.
   - No migration, no client decision.
2. **7b — meal sessions (S7-B, plus S7-F for meal sessions), after C5.**
   - Clean-up step approved separately, done before operations reference
     the sessions.
   - Migration M3 only if codes or uniqueness are approved.
3. **7c — master-data permissions (S7-C), after Q2.**
   - Either confirm the matrix as is (tests and documentation only), or
     plan the code split as its own approved change.
4. **Candidates S7-D, S7-E, S7-G, S7-H** only when individually approved.

---

## 10. Effort estimate (one developer)

The estimates include tests, the verification procedure and
documentation, as in Stages 4–6. They are developer-days, not calendar
days.

| Part | Work | Days |
|---|---|---|
| 7a | Search-select component and filtering helper (1); rollout to about ten pickers (1–1.5); unit, browser and regression tests (0.5–1) | **2.5–3.5** |
| 7b | Clean-up per C5 (0.5); M3 with codes and/or uniqueness (0.5); migration procedure and tests (0.5–1) | **1.5–2** |
| 7c | Matrix confirmed as is: tests and documentation | **0.5** |
| 7c (alternative) | Code split for receipts, master data and suppliers, with approved handling of older grants | **2–3** |
| — | Final verification and documentation (two full suites, PostgreSQL-only repeats, browser regressions, smoke tests) | **1–1.5** |
| S7-D | Prepared-food items for dishes | 1–1.5 |
| S7-E | Item-specific conversions | 2–3 |
| S7-F | Case-insensitive uniqueness (beyond meal sessions) | 0.5 |
| S7-G | Supplier screen for Kitchen Managers (protected file) | 0.25 |

| Scope | Total |
|---|---|
| Buildable now: 7a with verification | **3.5–5 days** |
| Core Stage 7 once C5 and Q2 are answered (7a + 7b + 7c without a code split) | **5.5–7.5 days** |
| Core with a code split | **7–10 days** |
| Every candidate as well | add **3.75–5.25 days** |

`REMAINING-WORK.md` row 5 shows 1–1.5 days. That figure predates counting
the pickers that need search, the permission gap in section 7 and the
verification procedure now used for every stage. It is left unchanged
here, because this is an assessment only, and should be updated when
Stage 7 is approved.

---

## 11. Readiness verdict

| Part | Ready? | Condition |
|---|---|---|
| 7a search-as-you-type | **Ready** | Your approval of scope and approach (P7-1, P7-2) |
| 7b meal sessions | **Blocked** | Client answer to C5; approval of the clean-up step |
| 7c master-data permissions | **Partly ready** | Matrix gives the roles; Q2 and P7-6 decide whether codes change |
| Candidates S7-D to S7-H | Not started | Individual decisions; S7-E also needs Q7 and Q8 |

No requirement status changes because of this assessment, and nothing is
ACCEPTED. The traceability matrix has no master-data rows. If Stage 7 is
approved, a cross-cutting "Master data (§5.7)" row could be added to
record evidence; that is a documentation decision, not done here.

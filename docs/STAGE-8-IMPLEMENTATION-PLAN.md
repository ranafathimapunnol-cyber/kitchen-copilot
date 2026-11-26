# Kitchen Copilot — Stage 8 Implementation Plan

## Outsourced food (OUT01–OUT03, AT04), with the PUR05 / STK01 supplier-return dependency

| | |
|---|---|
| Prepared | 24 November 2026, after Stage 6 (database `f3a8c2d61b47`) and Stage 7 S7-A (search-as-you-type pickers; frontend only) |
| Status | **Stage 8a built and tested 24 November 2026** (implementation instruction of 24 November 2026: "use sensible, safe interim defaults, document assumptions"); M6 `b8e4c2a9d175`. Stage 8b (Q6) and P8-6 not started. See section 12 for what was built and every interim default |
| Sources | `PROPOSAL.md` §4.2, §5.1 (PUR05), §5.2 (STK01), §5.4 (OUT01–OUT03), §5.8, §6, §9.5, §14 (AT04), §17.2 (Q4, Q6, Q7, Q11); `REQUIREMENTS-TRACEABILITY.md`; `REMAINING-WORK.md` rows 4 and 8; `STAGE-6-COMPLETION-REPORT.md`; `STAGE-7-READINESS-ASSESSMENT.md`; `CLIENT-QUESTIONS.md` §4, §6, §7; `BACKEND-COMPLETION-PLAN.md` (M6); the current models, routes and screens named below; read-only queries of the development database |

**Labels used below.** Every rule is marked as one of:
- **Approved requirement** — stated in the proposal or the approved
  permission matrix.
- **Client decision** — an open client question; nothing is assumed.
- **Project decision** — yours to approve before building.
- **Interim** — what would be built while a client question is open; it
  is not the client's answer.

---

## 1. Requirements and dependencies

### 1.1 Requirements in scope

| ID | Requirement (proposal) | Status today | Can be built before Q6? |
|---|---|---|---|
| **OUT01** | Track outsourced food separately: date, meal session, food item and supplier; ordered and received quantities; unit, unit rate, total cost; distributed and remaining; retained, returned, wasted, other disposal; costs linked to their source purchase records; kept separate from raw-ingredient stock | PENDING | **Yes**, except what a "returned" leftover does to the payable (Q6) |
| **OUT02** | Reports by period (daily, weekly, monthly, custom), supplier, item and meal session: received, distributed and leftover quantities, and purchase expenditure | PENDING | **Yes** |
| **OUT03** | Rejected deliveries and supplier returns recorded separately, referencing their sources; purchase totals and stock never counted twice; credits traceable | PENDING | **Partly:** recording rejected quantities, yes; returns, credits and their effect on what is owed need **Q6** |
| **AT04** | Outsourced breakfast report: received, distributed and leftover quantities, reconciling, with the linked purchase cost | PENDING | **Yes** (needs client question §6.1 to say which meals are outsourced) |
| PLAN08 (criterion 3) | "Compare prepared or received food quantities" | IN_PROGRESS (decision 6-9) | **Yes:** received quantities come from Stage 8 |

### 1.2 Dependent requirements, blocked by Q6

| ID | What is missing | Blocked by |
|---|---|---|
| **PUR05** | Supplier returns that reference the original purchase; returned goods leave stock through a movement; credits traceable and reflected in what is owed "according to the approved accounting rule"; original purchase unchanged | **Q6**. The standing rule keeps PUR05 on hold until Q6 is answered |
| **STK01** (criterion 3) | The ledger records supplier returns | PUR05 |
| OUT03 (criteria 2–4) | Outsourced returns and credits | **Q6** |

### 1.3 Dependencies on Stages 3–7

| Stage | What Stage 8 uses or changes |
|---|---|
| 3 — purchasing | **Bills** are the payable record: outsourced costs link to bill lines (OUT01 criterion 6) and appear once in what is owed (PUR04). **Purchase orders** stay for raw ingredients (section 2.1). Bill entry gains an optional link to an outsourced order |
| 4 — stock | **No outsourced food enters the raw-ingredient ledger** (OUT01 criterion 7). Today `accept_receipt` posts a movement for every accepted bill line whatever the item's kind, so Stage 8 must stop receipts from posting stock for items of kind OUTSOURCED (section 7). The append-only ledger and its triggers stay unchanged |
| 5 — meals | Distribution, remaining quantity and leftover classification already exist for prepared dishes (MEAL03–MEAL05). Stage 8 adds a third kind of dish line, **received (outsourced)**, so the same reconciliation and the same screen are used. Carried retained food stays as built (interim, Q11) |
| 6 — planning | `item_kind = OUTSOURCED` exists (classification by Admin and Kitchen Manager only). Outsourced items are not plannable "until the outsourced-food stage" (6-8); whether to allow them in plans is a project decision (P8-6). PLAN08 gains received quantities |
| 7 — S7-A | The supplier and item pickers on new screens use `SearchSelect`. S7-B (meal-session clean-up, C5) is not done, so outsourced records link to meal records only on the exact meal session (the S6-1 rule) |

---

## 2. Ordering, receiving and inventory

### 2.1 Proposed flow (project decision P8-1)

1. **Order.** An outsourced order is recorded:
   - meal date and meal session, supplier;
   - one or more OUTSOURCED items, each with ordered quantity, unit and
     unit rate (line total = quantity × rate);
   - statuses DRAFT → ORDERED, or CANCELLED with a reason.
2. **Bill.** The supplier's bill is entered as today (PUR01). Each bill line
   may be linked to one outsourced order line. The bill stays the only
   payable; the order's cost is the planned cost, shown against the billed
   cost.
3. **Delivery.** On or after the meal date:
   - per line: received quantity, rejected quantity with a reason, and
     accepted = received − rejected;
   - a delivery is confirmed once;
   - corrections by cancelling with a reason (the Stage 4 pattern).
   - **No stock movement is ever posted** (approved requirement, OUT01).
4. **Meal record.** Confirmed accepted quantities appear on the meal record
   of the same campus, date and exact meal session as "received" dish
   lines.
   - Distribution, remaining and leftovers use the existing rules:
     available = distributed + remaining; leftovers add up before closing.
   - A delivery for a date and session with no meal record waits until
     one exists. It is never linked to a same-named session (S6-1).
5. **Reports (OUT02, AT04):**
   - quantities from deliveries and meal records;
   - expenditure from the linked bill lines;
   - planned (order) cost shown separately, never added to expenditure.

### 2.2 Alternative considered

Reusing Stage 3 purchase orders and goods receipts for outsourced food was
considered and is not recommended:
- Purchase orders and receipts have no meal date or session.
- Receipts post stock.
- STAFF are excluded from purchase orders by decision (20 November 2026),
  which would block a Store Keeper from receiving outsourced food.

The proposal (§9.5 `outsourced_orders`) and the backend plan (M6) also
name a separate outsourced-order table.

### 2.3 Inventory integration

- Outsourced food is **not** raw-ingredient stock: no balance, low-stock
  entry, count or adjustment.
- Its trace is order → delivery (received, rejected, accepted) → meal
  record (distributed, remaining, leftovers) → bill (cost).
- **Guard:** receipts must not post stock for OUTSOURCED items (section 7),
  and kitchen issues, opening stock and counts must refuse them. Today an
  outsourced item can be selected in those forms, because nothing is
  classified yet.

---

## 3. Supplier returns: PUR05, STK01 and Q6

- **Q6** (§17.2): "How should supplier credits, rejected deliveries and
  outsourced-food returns affect payable balances and reports?" Client
  questions §4.2 ("How are supplier credits recorded?") and §6.3 ("How are
  rejected deliveries recorded?") are part of the same answer.
- **Can be built now:**
  - recording **rejected quantities at delivery**, separately (OUT03
    criterion 1), with no effect on the bill or what is owed (interim,
    Q6);
  - the meal leftover classification "returned to supplier" stays a
    classification only, as in Stage 5.
- **Waits for Q6** (8b, section 10):
  - supplier returns for raw ingredients (PUR05), with a SUPPLIER_RETURN
    stock movement (STK01 criterion 3) and the existing append-only rules;
  - credit notes and their effect on bill balances and supplier balances
    (PUR04);
  - outsourced returns and credits (OUT03 criteria 2–4);
  - reports that net credits.
- **Existing tables:**
  - `supplier_returns` (bill, date, status, credit amount, remarks) and
    `supplier_return_items` (bill line, quantity) exist from the initial
    schema and are unused (0 rows).
  - Whether they fit the answer to Q6 (credit notes, status values, a link
    to a stock movement or an outsourced line) is decided after Q6. Any
    change to them is a separately approved migration.
- **PUR05 stays on hold** (standing rule).

---

## 4. Data model, API and screens

### 4.1 Data model (migration M6; additive)

- **`outsourced_orders`:**
  - campus, number (`OO-00001` per campus), order date, meal date, meal
    session, supplier;
  - status (DRAFT, ORDERED, CANCELLED), notes;
  - created, ordered and cancelled by and at, cancellation reason.
- **`outsourced_order_lines`:**
  - order, item (OUTSOURCED kind at entry), ordered quantity (> 0), unit,
    unit rate (≥ 0), line total;
  - optional `purchase_item_id` (bill line, unique), the cost link.
- **`outsourced_deliveries`:** order, delivered date, status (DRAFT,
  CONFIRMED, CANCELLED), confirmed and cancelled by and at, reason.
- **`outsourced_delivery_lines`:**
  - order line, received (> 0), rejected (≥ 0), rejected ≤ received;
  - rejection reason, required when something is rejected;
  - accepted (= received − rejected; database check).
- **`meal_dishes` (Stage 5 table):**
  - add a nullable `source_delivery_line_id` (unique);
  - widen `ck_meal_dish_kind` to a third kind, "received": output 0,
    carried 0, received quantity = the accepted quantity, unit = the line's
    unit.
  - This changes a check constraint on an existing table (section 7).
- **Permission rows:** none if the existing `outsourced_food.*` codes are
  used (P8-3).
- **Audit entity types:** `OUTSOURCED_ORDER`, `OUTSOURCED_DELIVERY`.

### 4.2 API (sketch)

- `/api/outsourced-orders`:
  - options (sessions, OUTSOURCED items, suppliers, units);
  - list with filters (date, session, supplier, item, status);
  - create, detail and edit while DRAFT;
  - place, cancel (reason), history.
- `/api/outsourced-orders/{id}/deliveries`: record a delivery (received and
  rejected per line).
- `/api/outsourced-deliveries/{id}`: confirm, cancel (reason).
- **Bill link:** bill entry offers "against outsourced order" like "against
  purchase order", and bill detail shows the link. Uses `purchase_bill.*`
  checks as today.
- **Meal records:** `GET /api/meal-records/{id}` lists received lines with
  their source; the existing distribution endpoint works for them.
  Received lines are added automatically from confirmed deliveries, with no
  manual entry (P8-4).
- **Reports:** `GET /api/reports/outsourced-food` with period, supplier,
  item, meal session and `format=json|xlsx|pdf`, reusing
  `app/services/report_exports.py` (already used for PUR04 Excel and PDF)
  and a print view.
- **Guards:** receipts, kitchen issues, opening stock and counts refuse
  OUTSOURCED items (section 7).

### 4.3 Screens

- **Operations → Outsourced Food:**
  - list (status tabs, date range, supplier and item filters);
  - new order;
  - order detail: lines, ordered against received against billed, the
    delivery history, record delivery, confirm, cancel, history.
- **Meal record page:**
  - "Received (outsourced)" dish lines with a link to their order;
  - distribution and leftovers as for prepared dishes;
  - planned versus actual shows received quantities (PLAN08).
- **Bill entry and bill detail:** the outsourced-order link, alongside the
  purchase-order link.
- **Reports → Outsourced food:** period presets (today, this week, this
  month, custom), filters (supplier, item, meal session), totals that
  reconcile, purchase expenditure, Excel, PDF and print.

---

## 5. Roles and permissions

The approved matrix has no outsourced-food row. The user stories name
"Accounts or Kitchen Manager" (OUT01) and "Admin or Accounts" (OUT02).
Receiving goods is a Store Keeper duty in the matrix ("Record receipts").

| Role | Proposed (to approve) | Basis |
|---|---|---|
| **ADMIN** | Everything, including reports with costs | Matrix: Admin manages purchases and operational transactions |
| **KITCHEN_MANAGER** | Everything, including costs and reports | Holds `outsourced_food.*` and `purchase_bill.*` today (operational authority equal to Admin, decision 17 Nov 2026) |
| **STAFF as Store Keeper** | Record and confirm deliveries (received and rejected), view orders without prices | Matrix "Record receipts"; client question §6.2 open |
| **STAFF as Accounts** | Link bills, see costs and reports | Matrix "Record bills and payments", "View financial reports"; through `purchase_bill.*` |
| SUPER_ADMIN (target, not built) | None in campuses | Row 11 |

**Codes (project decision P8-3).**
- `outsourced_food.create/read/update` exist (module since the initial
  schema), are in the Kitchen Manager set and are **already
  STAFF-assignable**.
- **STAFF #3 already holds active `outsourced_food.create`, `.read` and
  `.update` grants.** As soon as endpoints use these codes, that user
  gains outsourced-food access with no grant change.
- Options:
  - (a) use the codes as they are, and hide costs unless the user holds
    `purchase_bill.read`;
  - (b) require the ADMIN or KITCHEN_MANAGER role for ordering and
    cancelling, and let the codes cover delivery recording and viewing.
- Either way, no grant is inserted, changed or deactivated.

**Recommendation:** option (b).
- Ordering and costs: ADMIN and KITCHEN_MANAGER.
- Recording deliveries: `outsourced_food.create/update`.
- Viewing: `outsourced_food.read`.
- Costs: only with `purchase_bill.read`.

STAFF #3's existing grants would then allow recording deliveries and
viewing orders without prices.

---

## 6. UI and UX consistency

- **Same patterns as purchase orders, receipts and meal records:**
  - list with status tabs and date filters;
  - number and status badge in the header;
  - draft → confirmed or ordered;
  - cancellation through the reason dialog (`ReasonModal`);
  - history with who, when and why.
- **Pickers:** `SearchSelect` for supplier and item (OUTSOURCED items
  only); meal session and menu as today.
- **Figures:** quantities shown with units (`plainQuantity`) and money with
  `formatRupees`.
- **Messages:** form errors before sending, with the API's wording on
  refusal; reconciliation messages as on meal records.
- **Layout:** 390 px phone width on every new screen; dialogs keep Escape
  behaviour (S7-A).
- **Report screen:** follows the purchases-versus-payments report (period
  presets, filters, Excel, PDF, print), with the reporting period, filters,
  quantities and units shown as §5.8 requires.

---

## 7. Migration and data-integrity risks

| Risk | Mitigation |
|---|---|
| **Receipts post stock for OUTSOURCED items today** (`accept_receipt`) | Stage 8 guard: refuse, or skip stock posting for, OUTSOURCED lines (P8-2). No item is classified on the development database, so nothing posted so far is affected. Tested on receipts, issues, opening stock and counts |
| An item with stock movements is later classified OUTSOURCED | Refuse classifying an item as OUTSOURCED while it has stock movements, or warn (P8-5). Changes Stage 6 classification behaviour, so it needs approval |
| Widening `ck_meal_dish_kind` on `meal_dishes` | Drop and recreate in M6, tested on the throwaway server (empty database and copy; `meal_dishes` has 0 rows on development); downgrade guard refuses while received lines exist; the carried-from foreign key and the planning triggers are left unchanged |
| A cost counted twice (order cost and bill cost) | Expenditure in reports comes only from bill lines; the order cost is labelled "planned"; one bill line links to at most one order line (unique); tests compare report totals with bill totals |
| Rejected quantities already billed | Recorded separately (OUT03 criterion 1); the effect on what is owed waits for Q6 and is shown as "rejected — credit not recorded (Q6)" |
| Exact meal-session matching (campus 1 has "Breakfast" and "breakfast") | Same-named sessions reported, never linked (S6-1); reports filter by exact session; AT04 ("outsourced breakfast") depends on the client's session answer (C5) |
| Units for outsourced food (portions, pieces, kg) | Explicit units only; no conversions assumed (Q7) |
| STAFF #3's dormant `outsourced_food.*` grants become active | Documented; P8-3 decides the scope; grants unchanged |
| Supplier-return tables shaped before Q6 | Not touched in 8a; any change in 8b after Q6, as its own migration |

**Migration procedure.** M6 follows the S7 procedure in
`DEVELOPMENT-SAFETY.md`:
- throwaway round trip on an empty database and on a copy of the
  development data, plus the API on the copy;
- the full PostgreSQL suite twice;
- a verified backup;
- exactly one revision applied, with read-only snapshots and fingerprints;
- code sync and read-only smoke tests.

Long runs go under `caffeinate -i`.

---

## 8. Test strategy and regression scope

- **Backend, SQLite and PostgreSQL:**
  - one test per OUT01 and OUT02 criterion, and OUT03 criterion 1;
  - AT04 end to end (order, bill, delivery with a rejection, meal record
    distribution and leftovers, report totals reconcile, linked cost
    shown);
  - no stock movement for outsourced food (fingerprint of the stock and
    purchasing tables);
  - the receipt, issue, opening and count guards;
  - four roles plus STAFF with the older `outsourced_food.*` grants;
    campus isolation;
  - audit rows;
  - concurrency: double confirmation, one bill line linked twice, a
    delivery racing order cancellation;
  - the widened meal-dish constraint on PostgreSQL;
  - report exports checked like `check_export_files.py`.
- **Migration:** round trips on an empty database and the copy; existing
  rows, grants, ledger triggers and planning triggers unchanged;
  `ck_meal_dish_kind` behaviour before and after; the downgrade guard.
- **Frontend:**
  - unit tests for line totals, received / rejected / accepted, and
    report period presets;
  - type check, lint and production build;
  - API types regenerated and compared with the running API.
- **Browser:** new outsourced-food suite (order, bill link, delivery with
  rejection, meal record reconciliation, report and exports, phone width,
  STAFF and other campus).
- **Regression:**
  - purchasing suites (payments, bills and report, exports, PUR01, PUR03,
    purchase orders);
  - Stage 4 suites (4a, 4b, 4c);
  - Stage 5 meals; Stage 6 planning; Stage 7 S7-A pickers.
- **Backend repeats:** the full PostgreSQL suite twice, and the
  PostgreSQL-only files five times.
- **After the sync:** read-only smoke tests on port 8000.

---

## 9. Client decisions needed before implementation

| # | Question | Needed for | Interim if 8a starts before the answer |
|---|---|---|---|
| 1 | **Client questions §6.1** — which meals are usually outsourced? | AT04 scope; screens | None needed; any session can be outsourced |
| 2 | **Client questions §6.2** — who confirms received quantities? | Delivery confirmation permission | Store Keeper duties through `outsourced_food.create/update` plus ADMIN and KITCHEN_MANAGER (P8-3 option b) |
| 3 | **Client questions §6.3** — how are rejected deliveries recorded? | OUT03 criterion 1 | Rejected quantity and reason per line at delivery; no effect on what is owed |
| 4 | **Q6** — effect of credits, rejected deliveries and outsourced returns on what is owed and on reports | PUR05, OUT03 criteria 2–4, STK01 criterion 3 | **None. Stage 8b is not built until answered** |
| 5 | **Q7** — units used for outsourced items (portions, pieces, kg) | Units on orders and deliveries | Existing units only; no conversions assumed |
| 6 | **Q11** — retained outsourced leftovers carried to another meal | Leftover handling | Stage 5 interim carry-forward applies |
| 7 | **Matrix gap** — who orders outsourced food and who sees its costs | Permissions | P8-3 option (b) |
| 8 | **C5** — four or five meal sessions; "Breakfast" / "breakfast" | AT04 ("outsourced breakfast") | Sessions as stored; same-named sessions reported, never linked |

### Project decisions (yours)

| # | Decision | Recommendation |
|---|---|---|
| P8-1 | Separate outsourced orders rather than reusing purchase orders and receipts | Separate tables (section 2.1) |
| P8-2 | Receipts with an OUTSOURCED item: refuse the line or skip stock posting | Refuse: outsourced food is received through outsourced deliveries, so it is never in raw stock |
| P8-3 | Permission scope for `outsourced_food.*` (STAFF #3 already holds them) | Option (b) in section 5 |
| P8-4 | Received lines on meal records: automatic from confirmed deliveries | Automatic, exact session only |
| P8-5 | Classifying an item OUTSOURCED when it has stock movements | Refuse (keeps the ledger explainable) |
| P8-6 | Outsourced items in meal plans | Allow planning received quantities (standards for OUTSOURCED items), so PLAN08 can compare planned with received; or keep them unplannable. Recommend allowing it, labelled interim |
| P8-7 | Split Stage 8 into 8a (now) and 8b (after Q6) | Yes |

---

## 10. Implementation sequence and estimate (one developer)

| Part | Content | Days |
|---|---|---|
| **8a.1** | M6 migration (four tables, the meal-dish kind, checks, audit types) and throwaway verification | 1–1.5 |
| **8a.2** | Orders, deliveries (received, rejected, accepted), bill-line link, guards on receipts, issues, opening stock and counts | 2–2.5 |
| **8a.3** | Meal-record integration (received lines, reconciliation, leftovers) and PLAN08 received quantities | 1–1.5 |
| **8a.4** | OUT02 report and AT04: period presets, filters, totals, Excel, PDF, print | 1.5–2 |
| **8a.5** | Screens: outsourced orders, deliveries, meal record, bill link, report | 2–2.5 |
| **8a.6** | Tests, browser suite, regressions, migration apply procedure, documentation | 1.5–2 |
| | **Stage 8a total** | **9–12 days** |
| **8b** | After Q6: PUR05 supplier returns with SUPPLIER_RETURN movements (STK01), credit notes and their effect on bill and supplier balances, outsourced returns and credits (OUT03), report netting; migration for the return tables if needed; verification | **3–4.5 days** |
| | **Stage 8 total** | **12–16.5 days** |

`REMAINING-WORK.md` row 8 shows 4–5 days. That figure predates:
- the meal-record integration;
- the receipt and stock guards;
- the bill link;
- the report exports;
- the verification procedure now used for every stage.

It is left unchanged here, and should be updated if this plan is approved.

### Expected statuses when 8a is built and tested

| Status | Requirements |
|---|---|
| TESTED | OUT01, OUT02, AT04, and PLAN08 (its received side completed) |
| IN_PROGRESS | OUT03 (criteria 2–4 wait for Q6) |
| PENDING | PUR05 (Q6) |
| IN_PROGRESS | STK01 (supplier returns wait for PUR05) |
| ACCEPTED | nothing without the client's confirmation |

---

## 11. Boundaries

- Planning only. Nothing is implemented until this plan is approved.
- No Stage 9 (dashboard and reports beyond OUT02) or Stage 10 (audit,
  security, users) work.
- PUR05 and the Q6-dependent parts stay on hold.
- No grant is inserted, changed or deactivated.
- No change to STAFF-assignable codes without approval.
- Protected files, `.env`, the Homebrew database on port 5432 and other
  containers are not touched.
- No commit, push or deploy. Nothing is marked ACCEPTED.

---

## 12. As built — Stage 8a (24 November 2026)

Implemented on the instruction to proceed with safe interim defaults and
document them. **Nothing here is a client decision**; each interim rule
below can be changed once the client answers.

### 12.1 What was built

| Part | As built |
|---|---|
| Migration M6 `b8e4c2a9d175` | `outsourced_orders`, `outsourced_order_lines`, `outsourced_deliveries`, `outsourced_delivery_lines`; `meal_dishes.received_quantity` (default 0) and `source_delivery_line_id` (unique) with a composite foreign key to the delivery line (id, accepted quantity, unit, campus); `ck_meal_dish_quantities`, `ck_meal_dish_available` and `ck_meal_dish_kind` widened to a third kind, "received". No permission row, grant or module. Downgrade refuses while orders or received lines exist |
| Orders | OO-numbered per campus; DRAFT → ORDERED, or CANCELLED with a reason; edit while DRAFT; meal date up to 30 days ahead (past meals can be recorded after the fact); OUTSOURCED items only; explicit unit, rate (4 decimals) and line total (planned cost) |
| Deliveries | OD-numbered; received, rejected (reason required) and accepted = received − rejected per line; DRAFT → CONFIRMED once, or CANCELLED with a reason; partial deliveries; dated between the order date and today |
| Meal records | Accepted food of a confirmed delivery becomes a "received" dish line on the OPEN record of the same campus, date and exact session — when the delivery is confirmed, when the record is created, or when it is reopened. Distribution and leftovers as for prepared dishes |
| Bill link | One supplier bill line per order line: same supplier, item and unit; linked and unlinked from the order page (`purchase_bill.update`); the bill detail shows the linked order |
| Guards | Goods receipts (entry, correction, acceptance — with the item rows locked), the receivable-bill list, kitchen issues and their options, opening stock, counts and their options, and the stock ledger itself refuse OUTSOURCED items; classification to OUTSOURCED refused for items with stock movements, opening stock, counts, draft receipts or draft issues; an item on outsourced orders stays OUTSOURCED |
| Report | `GET /api/outsourced-food/report` and `POST …/export` (Excel, PDF, audited); screen with Today / This week / This month / Custom, supplier, item and session filters, totals per unit, by item and by line, and a print view |
| Screens | Operations → Outsourced Food: list (status tabs, meal-date range, session, supplier, item), new order, order detail (edit draft, mark as ordered, cancel, record / correct / confirm / cancel deliveries, bill links, meal-record linkage, history), report. Meal record page: received lines with their order and delivery; "reconciliation pending" banner. Receipt screens: outsourced bill lines noted, not offered. Opening stock: outsourced items not offered |

### 12.2 Interim defaults (not client decisions)

| # | Interim rule | Why | Open question |
|---|---|---|---|
| I-1 | Orders are created, edited, placed and cancelled by ADMIN and KITCHEN_MANAGER only (role + code); deliveries need `outsourced_food.create` (record) and `.update` (edit, confirm, cancel a draft); viewing needs `.read`; cancelling a confirmed delivery is ADMIN and KITCHEN_MANAGER only | P8-3 option (b) | Matrix gap; client questions §6.2 |
| I-2 | Rates, totals, bill links and costs (screens, report, exports, history details) only for `purchase_bill.read`; STAFF #3 holds it, so STAFF #3 sees costs | Instruction | Matrix gap |
| I-3 | Accepted quantities across a line's deliveries never exceed the ordered quantity; an over-delivery is recorded as rejected or ordered separately | Keeps orders, bills and meal records consistent | §6.3 |
| I-4 | Rejected food is recorded with a reason only; no credit, return or change to what is owed. Shown as "Credit not recorded because client question Q6 … remains unresolved" | Q6 | Q6 |
| I-5 | A CLOSED meal record is never changed: confirmed food waits ("reconciliation pending") until an Admin or Kitchen Manager reopens it, then is added automatically | Instruction; proposal §4.2 | Historical corrections rule |
| I-6 | Cancelling a confirmed delivery is refused once its food has distribution or leftovers recorded, or while its meal record is closed, with the reason shown; otherwise its received lines are removed from the open record (audited) | Instruction | — |
| I-7 | An order cannot be cancelled while it has draft or confirmed deliveries or a linked bill line | Keeps the trace complete | — |
| I-8 | Cancelling a meal record releases its received lines (with their leftovers, kept in the audit row) so the food waits for the correct record of the same date and session | A wrongly created record must not trap delivered food | — |
| I-9 | Received lines keep their delivery's name, quantity and unit; only remarks change; they are not removed from the meal record directly | Single source: the delivery | — |
| I-10 | Exact meal-session matching; same-named sessions are reported, never linked | S6-1 | C5 |
| I-11 | Explicit units; a bill line links only in the order line's unit | Q7 | Q7 |
| I-12 | Bill lines for OUTSOURCED items are entered as usual and are never offered for goods receipts | P8-2 | — |

### 12.3 Deferred

- **Stage 8b** (after Q6): supplier returns (PUR05) with SUPPLIER_RETURN
  movements (STK01 criterion 3), credit notes, outsourced returns and
  credits (OUT03 criteria 2–4), report netting.
- **P8-6**: outsourced items in portion standards and meal plans (the Stage
  6 constraints stay RAW/PREPARED; the planning panel shows received food).

### 12.4 Verification

- Backend: `test_outsourced.py` (32, SQLite) and `test_outsourced_postgres.py`
  (8: constraints and races — double confirmation, one bill line linked
  twice, delivery against order cancellation, four deliveries at once,
  meal-record creation against confirmation, classification against
  opening stock); full PostgreSQL suite twice and the PostgreSQL-only files
  five times.
- Migration: round trip on an empty database (20 checks) and on a copy of
  the development data (50 checks, including every new database rule and
  the downgrade guard); the API end to end on the copy (33 checks).
- Frontend: unit tests (`outsourcedMath.test.mjs`), type check, lint,
  production build; Stage 8a browser suite (66 checks, 390 px and 1440 px included);
  purchasing, Stage 4–7 browser regressions.

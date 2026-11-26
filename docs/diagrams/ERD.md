# Kitchen Copilot — Entity Relationship Diagram (ERD)

## 0. Status of this document

| | |
|---|---|
| Describes | The database **as currently built** |
| Alembic revision | `b8e4c2a9d175` (Stage 8a, migration M6: outsourced orders, order lines, deliveries and delivery lines; `meal_dishes.received_quantity` and `source_delivery_line_id` with the received-line foreign key; the three meal-dish checks widened to a "received" kind; no permission row), applied to the Docker development database on 24 November 2026 after a verified backup; before it `f3a8c2d61b47` (Stage 6, migration M4: `items.item_kind`, portion standards, suggestion basis, meal plans and lines, their immutability triggers, `portion_standard` and `meal_plan` permission rows), applied to the Docker development database on 24 November 2026 after a verified backup; before it `ea00e5387c2f` (Stage 5, migration M5: meal records, dishes, leftovers, `meal` permission rows, applied 23 November 2026); `0e7d99065bd3` (Stage 4 slice 4c, M2c: stock counts, adjustments, `stock_count` permission rows, applied the same day); `c7d2e9f4a816` (slice 4b, M2b: kitchen issues and returns, append-only ledger triggers, applied the same day); `b5e1d7c3a920` (slice 4a, M2a: stock ledger columns, `stock_openings`, applied the same day); `a3c9e1f47b20` (Stage 3: purchase orders, bill-to-order links, `purchase_bill.*` permissions, applied 18 November 2026) and `e7b3c5a19d42` (PUR01). Each verified first on a throwaway PostgreSQL server (upgrade, downgrade, re-upgrade) |
| Verified against | The Docker development database (`kitchen_copilot_db`), 16 November 2026; stock tables re-read on 23 November 2026 at `b5e1d7c3a920` (30 tables, 83 foreign keys); kitchen tables and triggers added by `c7d2e9f4a816` the same day (34 tables, 106 foreign keys); count tables added by `0e7d99065bd3` the same day (37 tables, 120 foreign keys); meal tables added by `ea00e5387c2f` the same day (40 tables, 139 foreign keys); planning tables added by `f3a8c2d61b47` on 24 November 2026 (44 tables, 164 foreign keys); outsourced tables added by `b8e4c2a9d175` the same day (48 tables, 186 foreign keys) |
| Database | PostgreSQL 16 |
| Primary keys | `integer` (serial) on every table |

This ERD documents what exists today. The rest of the approved target design (organizations,
a single platform `SUPER_ADMIN`, outsourced food, attendance, hygiene, tasks, alerts and supplier
intelligence) is **not yet implemented**. See section 8 for the planned changes.
Do not treat anything in section 8 as existing.

## 1. Roles (current)

The database role enum `userrole` currently contains exactly three values.

| Role | Access today |
|---|---|
| `ADMIN` | Every campus permission, staff permission assignment, creation of Kitchen Manager and Staff accounts, permanent deletion of master data and waste records |
| `KITCHEN_MANAGER` | The same operational authority as `ADMIN`: every operational permission code (defined in code: `services/api/app/api/dependencies.py`), including suppliers, supplier bills, recording and viewing supplier payments, and supplier balances. Cannot create users, manage staff permissions or permanently delete records (see section 5) |
| `STAFF` | Only the permissions individually assigned by an `ADMIN` of the same campus, chosen from the staff-assignable list (see section 5) |

Every user belongs to exactly one campus (`users.campus_id` is required).

The approved target model adds one platform role, `SUPER_ADMIN` (exactly one
account, no campus, organization management only). It does not exist yet.

### Permission rules

- Permissions are stored as `module.action` codes in `permissions`.
- Allowed actions in the database today: `CREATE`, `READ`, `UPDATE`
  (enforced by `ck_permission_allowed_actions`). There is no `DELETE`
  permission; permanent deletion is restricted to the `ADMIN` role in code.
- `ADMIN` receives every permission row. `KITCHEN_MANAGER` receives a fixed set
  defined in code. `STAFF` receives only active rows in `staff_access_assignments`.
- Unauthorized actions are rejected by the backend, not only hidden in the frontend.

### Modules (14)

`dashboard`, `headcount`, `inventory`, `purchase_order` (genuine purchase
orders since 18 November 2026), `purchase_bill` ("Supplier Bills": bills,
payments, balances, the purchases-versus-payments report and attachments;
until 18 November 2026 these used `purchase_order.*`), `consumption`,
`outsourced_food`, `menu`, `audit`, `waste_tracking`, `stock_count` ("Stock
Counts": `stock_count.create` and `stock_count.read` only, added by migration
`0e7d99065bd3`, slice 4c), `meal` ("Meals": `meal.create`, `meal.read`,
`meal.update`, added by migration `ea00e5387c2f`, Stage 5), `portion_standard` ("Portion
Standards") and `meal_plan` ("Meal Plans"), each create, read and update, added
by migration `f3a8c2d61b47` (Stage 6; held by `KITCHEN_MANAGER`, not
STAFF-assignable, and the planning endpoints also require the `ADMIN` or
`KITCHEN_MANAGER` role). Older STAFF grants of
`purchase_order.*` were copied to `purchase_bill.*` by migration
`a3c9e1f47b20` and kept.

Permissions that exist but are not used by any endpoint yet: all
`outsourced_food.*` permissions, `headcount.create` and
`headcount.update` (`consumption.*` guards kitchen issues since slice 4b). `headcount.read` and `audit.read` are used only to
show the matching dashboard sections.

## 2. Campus isolation

Every operational table carries a required `campus_id` referencing `campuses`.
API queries filter by the authenticated user's campus. Exceptions without
`campus_id`: `campuses` itself, `modules`, `permissions` and
`staff_access_assignments` (scoped through the staff user's campus).

## 3. Mermaid ER diagram (as built)

To keep the diagram readable, not every foreign key (186 in all, 24 November
2026, after migration `b8e4c2a9d175`) is drawn as a relationship line. Among those shown only as `FK`
columns:

- `campus_id` → `campuses` on `items`, `unit_conversions`, `menus`,
  `menu_main_items`, `purchases`, `purchase_items`, `goods_receipts`,
  `goods_receipt_items`, `stock_movements`, `stock_openings`,
  `kitchen_issues`, `kitchen_issue_items`, `kitchen_returns`,
  `kitchen_return_items`, `stock_counts`, `stock_count_items`,
  `stock_adjustments`, `meal_records`, `meal_dishes`, `meal_leftovers`,
  `portion_standards`, `portion_standard_basis`, `meal_plans`,
  `meal_plan_lines`, `supplier_payments`, `supplier_returns`,
  `supplier_return_items`, `waste_records` and `waste_items` (see
  section 2);
- user references → `users`: `goods_receipts.created_by`,
  `goods_receipts.accepted_by`, `stock_movements.created_by`,
  `stock_openings.created_by`, `stock_openings.reversed_by`, the
  `created_by`, `confirmed_by`, `cancelled_by` and `reversed_by` columns of
  `kitchen_issues` and `kitchen_returns`, `stock_counts.counted_by`, the
  `counted_by`, `raised_by` and `decided_by` columns of
  `stock_adjustments`, the `created_by`, `closed_by`, `reopened_by` and
  `cancelled_by` columns of `meal_records`, `meal_dishes.created_by`,
  `meal_leftovers.created_by`, the `created_by`, `approved_by` and
  `cancelled_by` columns of `portion_standards` and `meal_plans`,
  `supplier_payments.created_by`,
  `supplier_returns.created_by` and `waste_records.recorded_by`;
- unit references → `units`: `unit_id` and `standard_unit_id` on
  `kitchen_issue_items`, `kitchen_return_items` and `stock_count_items`;
  `unit_id` on `meal_dishes` and `meal_leftovers`; `unit_id` on
  `portion_standards` and `portion_standard_basis`; `override_unit_id`,
  `standard_unit_id`, `unit_id` and `base_unit_id` on `meal_plan_lines`.

`stock_movements.reference_type` and `reference_id` name the document that
posted a movement (`GOODS_RECEIPT` → `goods_receipts`, `STOCK_OPENING` →
`stock_openings`, `KITCHEN_ISSUE` → `kitchen_issues`, `KITCHEN_RETURN` →
`kitchen_returns`, `STOCK_ADJUSTMENT` → `stock_adjustments`). That link has no foreign key; `source_key` (unique per
campus) is the database guard that a source posts only once.

```mermaid
erDiagram
    campuses ||--o{ users : employs
    campuses ||--o{ audit_logs : records
    users o|--o{ audit_logs : performed_by

    modules ||--o{ permissions : groups
    permissions ||--o{ staff_access_assignments : granted
    users ||--o{ staff_access_assignments : receives
    users ||--o{ staff_access_assignments : assigned_by

    campuses ||--o{ categories : owns
    campuses ||--o{ units : owns
    units ||--o{ unit_conversions : from_unit
    units ||--o{ unit_conversions : to_unit
    categories ||--o{ items : classifies
    units ||--o{ items : standard_unit
    campuses ||--o{ suppliers : owns
    campuses ||--o{ meal_sessions : has
    meal_sessions ||--o{ menus : session
    menus ||--o{ menu_main_items : ingredients
    items ||--o{ menu_main_items : item
    units ||--o{ menu_main_items : unit

    suppliers ||--o{ purchases : bills
    users ||--o{ purchases : created_by
    purchases ||--o{ purchase_items : lines
    items ||--o{ purchase_items : item
    units ||--o{ purchase_items : unit
    purchases ||--o{ goods_receipts : received_as
    goods_receipts ||--o{ goods_receipt_items : lines
    purchase_items ||--o{ goods_receipt_items : against
    purchases ||--o{ supplier_payments : paid_by
    purchases ||--o{ supplier_returns : returned_against
    purchases ||--o{ purchase_attachments : "attached files"
    suppliers ||--o{ purchase_orders : "ordered from"
    purchase_orders ||--|{ purchase_order_items : "order lines"
    purchase_orders |o--o{ purchases : "billed by"
    purchase_order_items |o--o{ purchase_items : "billed by"
    supplier_returns ||--o{ supplier_return_items : lines
    purchase_items ||--o{ supplier_return_items : against

    items ||--o{ stock_movements : ledger
    units ||--o{ stock_movements : unit
    goods_receipt_items o|--o| stock_movements : posted_once
    stock_movements |o--o| stock_movements : "reversed by (at most once)"
    items ||--o{ stock_openings : "opening stock"
    units ||--o{ stock_openings : "entered unit"
    units ||--o{ stock_openings : "standard unit"
    meal_sessions ||--o{ kitchen_issues : "issued for"
    menus ||--o{ kitchen_issues : "issued for"
    kitchen_issues ||--|{ kitchen_issue_items : lines
    items ||--o{ kitchen_issue_items : item
    kitchen_issues ||--o{ kitchen_returns : "unused returned"
    kitchen_returns ||--|{ kitchen_return_items : lines
    kitchen_issue_items ||--o{ kitchen_return_items : "returned from"
    stock_counts ||--|{ stock_count_items : lines
    items ||--o{ stock_count_items : counted
    stock_counts ||--o{ stock_adjustments : "raised from"
    stock_count_items ||--o| stock_adjustments : "adjustment (at most one)"
    items ||--o{ stock_adjustments : item
    meal_sessions ||--o{ meal_records : "meal of"
    meal_records ||--o{ meal_dishes : dishes
    menus o|--o{ meal_dishes : menu
    meal_dishes ||--o{ meal_leftovers : "leftovers (one per class)"
    meal_leftovers |o--o| meal_dishes : "carried forward once (interim, Q11)"
    menus ||--o{ portion_standards : "standards (versioned)"
    items ||--o{ portion_standards : item
    portion_standards ||--o{ portion_standard_basis : "suggested from (PLAN03)"
    meal_records ||--o{ portion_standard_basis : basis
    meal_sessions ||--o{ meal_plans : "plan of"
    menus ||--o{ meal_plans : menu
    meal_plans ||--o{ meal_plan_lines : "main items"
    items ||--o{ meal_plan_lines : item
    portion_standards o|--o{ meal_plan_lines : "standard used (snapshot)"
    meal_sessions ||--o{ outsourced_orders : "meal of (exact session)"
    suppliers ||--o{ outsourced_orders : supplier
    outsourced_orders ||--|{ outsourced_order_lines : "food ordered"
    items ||--o{ outsourced_order_lines : "OUTSOURCED item"
    purchase_items |o--o| outsourced_order_lines : "billed by (one each)"
    outsourced_orders ||--o{ outsourced_deliveries : deliveries
    outsourced_deliveries ||--|{ outsourced_delivery_lines : "received, rejected, accepted"
    outsourced_order_lines ||--o{ outsourced_delivery_lines : "delivered against"
    outsourced_delivery_lines |o--o| meal_dishes : "received line (once)"

    campuses ||--o{ daily_headcounts : counts

    waste_records ||--o{ waste_items : lines
    meal_sessions o|--o{ waste_records : session
    items o|--o{ waste_items : raw_item
    menus o|--o{ waste_items : menu
    units ||--o{ waste_items : unit

    campuses {
        int id PK
        varchar name UK
        varchar code UK
        boolean is_active
    }
    users {
        int id PK
        int campus_id FK
        varchar full_name
        varchar email UK
        varchar password_hash
        userrole role "ADMIN, KITCHEN_MANAGER, STAFF"
        boolean is_active
    }
    audit_logs {
        int id PK
        int campus_id FK
        int user_id FK "nullable"
        varchar action
        varchar entity_type
        int entity_id "nullable"
        json details
        timestamptz created_at
    }
    modules {
        int id PK
        varchar name
        varchar code UK
    }
    permissions {
        int id PK
        int module_id FK
        varchar action "CREATE, READ, UPDATE"
        varchar permission_code UK
    }
    staff_access_assignments {
        int id PK
        int staff_user_id FK
        int permission_id FK
        int assigned_by FK
        boolean is_active
        timestamptz assigned_at
        timestamptz updated_at
    }
    categories {
        int id PK
        int campus_id FK
        varchar name
        varchar description
        boolean is_active
        timestamptz created_at
    }
    units {
        int id PK
        int campus_id FK
        varchar name
        varchar symbol
        varchar dimension "weight, volume, count, other"
        boolean is_active
    }
    unit_conversions {
        int id PK
        int campus_id FK
        int from_unit_id FK
        int to_unit_id FK
        numeric factor "18,6 and > 0"
    }
    items {
        int id PK
        int campus_id FK
        varchar name
        int category_id FK
        int standard_unit_id FK
        numeric minimum_stock "18,3"
        varchar description
        boolean is_active
        varchar item_kind "RAW, PREPARED, OUTSOURCED; null = not classified"
    }
    suppliers {
        int id PK
        int campus_id FK
        varchar name
        varchar phone
        varchar email
        varchar address
        boolean is_active
    }
    meal_sessions {
        int id PK
        int campus_id FK
        varchar name
        boolean is_active
    }
    menus {
        int id PK
        int campus_id FK
        varchar name
        int meal_session_id FK
        boolean is_active
    }
    menu_main_items {
        int id PK
        int campus_id FK
        int menu_id FK
        int item_id FK
        numeric quantity_per_person "18,3 and > 0"
        int unit_id FK
    }
    purchases {
        int id PK
        int campus_id FK
        int supplier_id FK
        varchar invoice_number
        date purchase_date
        numeric subtotal "18,2"
        numeric discount "18,2"
        numeric extra_charges "18,2"
        numeric grand_total "18,2"
        text remarks
        varchar bill_attachment_path "unused; see purchase_attachments"
        varchar status "currently always DRAFT"
        int created_by FK
        timestamptz created_at
        timestamptz duplicate_reviewed_at
        int duplicate_reviewed_by FK
        varchar duplicate_review_note "500"
        int purchase_order_id FK "nullable"
    }
    purchase_orders {
        int id PK
        int campus_id FK
        int order_seq "unique per campus"
        varchar order_number "PO-00001, unique per campus"
        int supplier_id FK
        date order_date
        date expected_date "nullable, not before order_date"
        varchar status "DRAFT, PLACED, CLOSED, CANCELLED"
        varchar remarks "1000"
        int created_by FK
        timestamptz created_at
        timestamptz updated_at
        int placed_by FK
        timestamptz placed_at
        int closed_by FK
        timestamptz closed_at
        varchar close_reason "500"
        int cancelled_by FK
        timestamptz cancelled_at
        varchar cancel_reason "500"
    }
    purchase_order_items {
        int id PK
        int campus_id FK
        int purchase_order_id FK
        int item_id FK "unique per order"
        numeric quantity "18,3; > 0"
        int unit_id FK
        varchar remarks "500"
    }
    purchase_attachments {
        int id PK
        int campus_id FK
        int purchase_id FK
        varchar object_key "255, unique; private storage key"
        varchar original_filename "255"
        varchar content_type "pdf, jpeg, png or webp"
        bigint size_bytes "> 0"
        varchar checksum_sha256 "64; unique per bill"
        varchar remarks "500"
        int uploaded_by FK
        timestamptz uploaded_at
    }
    purchase_items {
        int id PK
        int campus_id FK
        int purchase_id FK
        int item_id FK
        numeric quantity "18,3"
        int unit_id FK
        numeric unit_rate "18,4"
        numeric line_total "18,2"
        varchar remarks
        int purchase_order_item_id FK "nullable"
    }
    goods_receipts {
        int id PK
        int campus_id FK
        int purchase_id FK
        date receipt_date
        varchar status "DRAFT, ACCEPTED"
        text remarks
        int accepted_by FK
        timestamptz accepted_at
        int created_by FK
        timestamptz created_at
    }
    goods_receipt_items {
        int id PK
        int campus_id FK
        int receipt_id FK
        int purchase_item_id FK
        numeric quantity_received "18,3"
        numeric quantity_accepted "18,3"
        numeric quantity_rejected "18,3"
        varchar remarks
    }
    supplier_payments {
        int id PK
        int campus_id FK
        int purchase_id FK
        date payment_date
        numeric amount "18,2 and > 0"
        varchar payment_method
        varchar reference_number
        varchar remarks
        int created_by FK
        timestamptz created_at
    }
    supplier_returns {
        int id PK
        int campus_id FK
        int purchase_id FK
        date return_date
        varchar status
        numeric credit_amount "18,2"
        text remarks
        int created_by FK
        timestamptz created_at
    }
    supplier_return_items {
        int id PK
        int campus_id FK
        int return_id FK
        int purchase_item_id FK
        numeric quantity "18,3"
        numeric unit_rate "18,4"
        numeric line_total "18,2"
        varchar remarks
    }
    stock_movements {
        int id PK
        int campus_id FK
        int item_id FK
        varchar movement_type "OPENING, RECEIPT, REVERSAL posted today; ISSUE, UNUSED_RETURN, ADJUSTMENT, SUPPLIER_RETURN allowed"
        smallint direction "+1 in, -1 out"
        numeric quantity "18,3 and > 0, item standard unit"
        int unit_id FK "item standard unit"
        int receipt_item_id FK "nullable"
        varchar reference_type "GOODS_RECEIPT, STOCK_OPENING"
        int reference_id "no FK"
        varchar source_key "unique per campus"
        int reversal_of_id FK "nullable, REVERSAL only, unique"
        timestamptz effective_at "when the stock moved"
        varchar remarks
        int created_by FK
        timestamptz created_at "when it was posted"
    }
    stock_openings {
        int id PK
        int campus_id FK
        int item_id FK
        numeric quantity "18,3 and > 0, as entered"
        int unit_id FK "entered unit"
        numeric conversion_factor "24,12 and > 0, factor used"
        numeric standard_quantity "18,3 and > 0"
        int standard_unit_id FK
        date effective_date "today or earlier"
        varchar remarks
        varchar status "ACTIVE, REVERSED"
        int created_by FK
        timestamptz created_at
        int reversed_by FK "nullable"
        timestamptz reversed_at "nullable"
        varchar reversal_reason "nullable"
    }
    kitchen_issues {
        int id PK
        int campus_id FK
        int issue_seq "unique per campus"
        varchar issue_number "KI-00001, unique per campus"
        date issue_date "today or earlier"
        int meal_session_id FK
        int menu_id FK "of that session"
        varchar remarks
        varchar status "DRAFT, CONFIRMED, CANCELLED, REVERSED"
        timestamptz effective_at "set on confirmation"
        int created_by FK "responsible user"
        timestamptz created_at
        timestamptz updated_at
        int confirmed_by FK
        timestamptz confirmed_at
        int cancelled_by FK
        timestamptz cancelled_at
        varchar cancellation_reason
        int reversed_by FK
        timestamptz reversed_at
        varchar reversal_reason
    }
    kitchen_issue_items {
        int id PK
        int campus_id FK
        int issue_id FK
        int item_id FK "once per issue"
        numeric quantity "18,3 and > 0, as entered"
        int unit_id FK
        numeric conversion_factor "24,12 and > 0"
        numeric standard_quantity "18,3 and > 0"
        int standard_unit_id FK
        varchar remarks
    }
    kitchen_returns {
        int id PK
        int campus_id FK
        int return_seq "unique per campus"
        varchar return_number "KR-00001, unique per campus"
        int issue_id FK
        date return_date "not before the issue date"
        varchar status "DRAFT, CONFIRMED, CANCELLED, REVERSED"
        timestamptz effective_at "never before the issue"
        int created_by FK
        int confirmed_by FK
        int cancelled_by FK
        int reversed_by FK
    }
    kitchen_return_items {
        int id PK
        int campus_id FK
        int return_id FK
        int issue_item_id FK "once per return"
        numeric quantity "18,3 and > 0"
        int unit_id FK
        numeric conversion_factor "24,12 and > 0"
        numeric standard_quantity "18,3 and > 0"
        int standard_unit_id FK
        varchar remarks
    }
    stock_counts {
        int id PK
        int campus_id FK
        int count_seq "unique per campus"
        varchar count_number "SC-00001, unique per campus"
        timestamptz counted_at "when saved; the count time"
        int counted_by FK "the verifier"
        varchar reason "required"
        varchar remarks
    }
    stock_count_items {
        int id PK
        int campus_id FK
        int count_id FK
        int item_id FK "once per count"
        numeric quantity "18,3 and >= 0, as counted"
        int unit_id FK
        numeric conversion_factor "24,12 and > 0"
        numeric standard_quantity "18,3 and >= 0, physical"
        int standard_unit_id FK
        numeric system_balance "18,3, when saved"
        numeric difference "physical - system balance"
        varchar remarks
    }
    stock_adjustments {
        int id PK
        int campus_id FK
        int count_id FK "with counted_by, to stock_counts"
        int count_item_id FK "unique; with count_id, item_id"
        int item_id FK
        int counted_by FK "copied from the count"
        varchar reason "required"
        varchar status "PENDING, APPROVED, REJECTED"
        int raised_by FK
        timestamptz raised_at
        int decided_by FK "never the counter"
        timestamptz decided_at
        varchar decision_reason "required when REJECTED"
    }
    meal_records {
        int id PK
        int campus_id FK
        date meal_date
        int meal_session_id FK "one live record per date and session"
        varchar status "OPEN, CLOSED, CANCELLED"
        int expected_students ">= 0"
        int expected_staff ">= 0"
        int expected_guests ">= 0"
        int actual_students "null until recorded"
        int actual_staff "null until recorded"
        int actual_guests "null until recorded"
        int created_by FK
        int closed_by FK "latest closing"
        json closed_usage "net usage per item at closing"
        int reopened_by FK "latest reopening, with reason"
        int reopen_count
        int cancelled_by FK
    }
    meal_dishes {
        int id PK
        int campus_id FK
        int meal_record_id FK
        varchar dish_name "free text (5-3)"
        int menu_id FK "nullable"
        int unit_id FK
        numeric output_quantity "18,3; 0 for carried-in and received"
        numeric carried_quantity "18,3; 0 for prepared and received"
        numeric received_quantity "18,3; accepted outsourced food (Stage 8a)"
        numeric available_quantity "output + carried + received"
        numeric distributed_quantity "null until recorded"
        numeric remaining_quantity "available - distributed"
        int source_leftover_id FK "unique; carried-in only"
        int source_dish_id FK
        int source_meal_record_id FK
        int source_delivery_line_id FK "unique; received only (Stage 8a)"
    }
    outsourced_orders {
        int id PK
        int campus_id FK
        varchar order_number UK "OO-00001 per campus"
        date order_date
        date meal_date
        int meal_session_id FK "exact session"
        int supplier_id FK
        varchar status "DRAFT, ORDERED, CANCELLED"
        int created_by FK
        int ordered_by FK
        int cancelled_by FK "with reason"
    }
    outsourced_order_lines {
        int id PK
        int campus_id FK
        int order_id FK
        int item_id FK "OUTSOURCED at entry"
        numeric ordered_quantity "18,3 and > 0"
        int unit_id FK "explicit (Q7)"
        numeric unit_rate "18,4; planned"
        numeric line_total "18,2; planned cost"
        int purchase_item_id FK "unique; the bill line"
        int linked_by FK
    }
    outsourced_deliveries {
        int id PK
        int campus_id FK
        varchar delivery_number UK "OD-00001 per campus"
        int order_id FK
        date delivery_date
        varchar status "DRAFT, CONFIRMED, CANCELLED"
        int confirmed_by FK
        int cancelled_by FK "with reason"
    }
    outsourced_delivery_lines {
        int id PK
        int campus_id FK
        int delivery_id FK
        int order_id FK
        int order_line_id FK "same order and unit"
        int unit_id FK
        numeric received_quantity "> 0"
        numeric rejected_quantity "0..received; reason required"
        numeric accepted_quantity "received - rejected"
    }
    meal_leftovers {
        int id PK
        int campus_id FK
        int meal_record_id FK
        int dish_id FK "with record, campus, unit"
        varchar classification "RETAINED, RETURNED_TO_SUPPLIER, WASTED, DISPOSED"
        numeric quantity "18,3 and > 0"
        int unit_id FK "the dish's unit"
        varchar remarks "required"
    }
    portion_standards {
        int id PK
        int campus_id FK
        int menu_id FK
        int item_id FK
        numeric quantity_per_person "18,3 and > 0"
        int unit_id FK "item's unit or an explicit conversion"
        date effective_from
        int version_no "set at approval; unique per menu and item"
        varchar status "DRAFT, APPROVED, CANCELLED"
        varchar source "MANUAL, COPIED, SUGGESTED"
        int copied_from_menu_main_item_id "plain reference, no FK"
        varchar item_kind "RAW or PREPARED, copied at approval"
        int created_by FK
        int approved_by FK
        int cancelled_by FK
    }
    portion_standard_basis {
        int id PK
        int campus_id FK
        int standard_id FK
        int meal_record_id FK
        numeric quantity_used "net usage at closing, > 0"
        int unit_id FK "item's standard unit"
        int people_served "> 0"
    }
    meal_plans {
        int id PK
        int campus_id FK
        int plan_seq
        varchar plan_number "MP-00001 per campus"
        date plan_date
        int meal_session_id FK "one live plan per date and session"
        int menu_id FK
        int expected_headcount ">= 1"
        varchar status "DRAFT, APPROVED, CANCELLED"
        int created_by FK
        int approved_by FK "kept when cancelled"
        int cancelled_by FK "with a reason"
    }
    meal_plan_lines {
        int id PK
        int campus_id FK
        int plan_id FK
        int item_id FK "unique per plan"
        numeric override_quantity_per_person "one-day override"
        int override_unit_id FK
        varchar override_reason "required with an override"
        int standard_id FK "snapshot at approval"
        varchar item_kind "snapshot"
        numeric standard_quantity_per_person "snapshot"
        int standard_unit_id FK "snapshot"
        numeric quantity_per_person "snapshot: used"
        int unit_id FK "snapshot: used"
        numeric required_quantity "snapshot; count units rounded up"
        boolean rounded_up "snapshot"
        int base_unit_id FK "snapshot"
        numeric conversion_factor "24,12 snapshot"
        numeric required_base_quantity "snapshot"
    }
    daily_headcounts {
        int id PK
        int campus_id FK
        date headcount_date
        int student_count ">= 0"
        timestamptz created_at
    }
    waste_records {
        int id PK
        int campus_id FK
        date waste_date
        int meal_session_id FK "nullable"
        int recorded_by FK
        text notes
        timestamptz created_at
        timestamptz updated_at
    }
    waste_items {
        int id PK
        int campus_id FK
        int waste_record_id FK
        int item_id FK "required for RAW_INGREDIENT"
        int menu_id FK "nullable"
        int unit_id FK
        varchar food_name
        varchar waste_type "RAW_INGREDIENT, PREPARED_FOOD"
        numeric quantity "18,3 and > 0"
        varchar waste_stage
        varchar waste_reason
        numeric estimated_cost "18,2"
    }
```

## 4. Constraints enforced by the database

| Table | Unique constraints | Check constraints |
|---|---|---|
| `campuses` | `name`; `code` | — |
| `users` | `email` | — |
| `modules` | `code` | — |
| `permissions` | `permission_code`; `(module_id, action)` | `action IN (CREATE, READ, UPDATE)` |
| `staff_access_assignments` | `(staff_user_id, permission_id)` | — |
| `categories` | `(campus_id, name)` | — |
| `units` | `(campus_id, name)`; `(campus_id, symbol)` | — |
| `unit_conversions` | `(campus_id, from_unit_id, to_unit_id)` | `factor > 0` |
| `items` | `(campus_id, name)` | `minimum_stock >= 0` |
| `suppliers` | `(campus_id, name)` | — |
| `meal_sessions` | `(campus_id, name)` (case-sensitive) | — |
| `menus` | `(campus_id, name)` | — |
| `menu_main_items` | `(campus_id, menu_id, item_id)` | `quantity_per_person > 0` |
| `purchases` | `(campus_id, supplier_id, invoice_number)` | discount, extra charges, subtotal, grand total `>= 0` |
| `purchase_items` | — | `quantity > 0`; `unit_rate >= 0`; `line_total >= 0` |
| `goods_receipt_items` | — | received `> 0`; accepted, rejected `>= 0`; accepted + rejected `<= received` |
| `stock_movements` | `(campus_id, receipt_item_id)` — a receipt line can post stock only once; `(campus_id, source_key)` — any source posts only once; `reversal_of_id` — a movement is reversed at most once | `quantity > 0`; `direction IN (1, -1)`; `movement_type` one of seven values; OPENING, RECEIPT and UNUSED_RETURN add stock (+1); ISSUE and SUPPLIER_RETURN remove it (−1); `reversal_of_id` is set exactly when the type is REVERSAL |
| `stock_openings` | Partial unique index `uq_stock_opening_active_item` on `(campus_id, item_id) WHERE status = 'ACTIVE'` — one active opening per item per campus; reversed entries stay | `quantity`, `standard_quantity`, `conversion_factor` `> 0`; `status IN (ACTIVE, REVERSED)`; status REVERSED exactly when `reversed_at`, `reversed_by` and `reversal_reason` are all set |
| `supplier_payments` | — | `amount > 0` |
| `purchase_attachments` | `object_key`; `(purchase_id, checksum_sha256)` | `size_bytes > 0` |
| `purchases` review columns | — | `duplicate_reviewed_at` and `duplicate_reviewed_by` both set or both empty |
| `purchase_orders` | `(campus_id, order_seq)`; `(campus_id, order_number)` | status is one of four values; `expected_date` not before `order_date`; placed, closed and cancelled user and time both set or both empty |
| `purchase_order_items` | `(purchase_order_id, item_id)` | `quantity > 0` |
| `supplier_return_items` | — | `quantity > 0`; `unit_rate >= 0` |
| `daily_headcounts` | `(campus_id, headcount_date)` | `student_count >= 0` |
| `waste_items` | — | `quantity > 0`; `estimated_cost >= 0`; type, stage and reason lists; RAW_INGREDIENT requires `item_id`; PREPARED_FOOD requires no `item_id` and a non-empty `food_name` |
| `kitchen_issues` | `(campus_id, issue_seq)`; `(campus_id, issue_number)` | status is one of four values; CONFIRMED or REVERSED exactly when `confirmed_at`, `confirmed_by` and `effective_at` are set; CANCELLED exactly when the three cancellation fields are set; REVERSED exactly when the three reversal fields are set |
| `kitchen_issue_items` | `(issue_id, item_id)` | `quantity`, `standard_quantity`, `conversion_factor` `> 0` |
| `kitchen_returns` | `(campus_id, return_seq)`; `(campus_id, return_number)` | the same four status rules as `kitchen_issues` |
| `kitchen_return_items` | `(return_id, issue_item_id)` | `quantity`, `standard_quantity`, `conversion_factor` `> 0` |
| `stock_counts` | `(campus_id, count_seq)`; `(campus_id, count_number)`; `(id, counted_by)` (target of the counter foreign key) | — |
| `stock_count_items` | `(count_id, item_id)`; `(id, count_id, item_id)` (target of the count-line foreign key) | `quantity`, `standard_quantity` `>= 0`; `conversion_factor > 0`; `difference` = `standard_quantity` − `system_balance` |
| `meal_records` | Partial unique index `uq_meal_record_session_date` on `(campus_id, meal_date, meal_session_id) WHERE status <> 'CANCELLED'` | status one of three; expected counts `>= 0`; actual counts all three or none, `>= 0`; CLOSED needs `closed_at` and actual counts; closing, cancellation and reopening fields complete together (`reopen_count` 0 exactly when never reopened) |
| `outsourced_orders` | `(campus_id, order_seq)`, `(campus_id, order_number)`; `(id, campus_id)` (target of the line and delivery keys) | status one of three; ordered by and at together; ORDERED has an ordered time; CANCELLED exactly when cancelled at, by and reason are set |
| `outsourced_order_lines` | `(order_id, item_id)`; `purchase_item_id` — one bill line bills one order line; `(id, order_id, campus_id, unit_id)` (target of the delivery-line key); composite foreign key `(order_id, campus_id)` → `outsourced_orders` | `ordered_quantity > 0`; `unit_rate >= 0`; `line_total >= 0`; the bill link, linked at and linked by set together |
| `outsourced_deliveries` | `(campus_id, delivery_seq)`, `(campus_id, delivery_number)`; `(id, order_id, campus_id)`; composite foreign key `(order_id, campus_id)` → `outsourced_orders` | status one of three; CONFIRMED has a confirmation time; confirmed by and at together; CANCELLED exactly when cancelled at, by and reason are set |
| `outsourced_delivery_lines` | `(delivery_id, order_line_id)`; `(id, accepted_quantity, unit_id, campus_id)` (target of the received-line key); composite foreign keys `(delivery_id, order_id, campus_id)` → `outsourced_deliveries` and `(order_line_id, order_id, campus_id, unit_id)` → `outsourced_order_lines` — same order, campus and unit | `received_quantity > 0`; `0 <= rejected_quantity <= received_quantity`; accepted = received − rejected; a reason when anything is rejected |
| `meal_dishes` | `source_delivery_line_id` — a delivery line is received once (migration `b8e4c2a9d175`); composite foreign key `fk_meal_dish_received_from` `(source_delivery_line_id, received_quantity, unit_id, campus_id)` → `outsourced_delivery_lines` — the received line matches the accepted quantity, unit and campus, and the delivery line cannot change or be deleted while received; `source_leftover_id` — a retained line is carried at most once; `(id, meal_record_id, campus_id, unit_id)` (target of the leftover foreign key); composite foreign key `fk_meal_dish_carried_from` `(source_leftover_id, source_dish_id, source_meal_record_id, campus_id, source_classification, carried_quantity, unit_id)` → `meal_leftovers` — the carried line matches its source exactly, and the source cannot be changed or deleted while carried | quantities `>= 0`; available = output + carried + received; a prepared dish has output and no source, a carried-in line has the carried quantity, a RETAINED source and no output, a received line has the received quantity, a source delivery line and no output or carried quantity (three kinds, widened by `b8e4c2a9d175`); never its own source; distributed and remaining set together, `>= 0`, and available = distributed + remaining; name not blank |
| `meal_leftovers` | `(dish_id, classification)` — one line per classification per dish; `(id, dish_id, meal_record_id, campus_id, classification, quantity, unit_id)` (target of the carried-from key); composite foreign key `(dish_id, meal_record_id, campus_id, unit_id)` → `meal_dishes` — same record, campus and unit as the dish | classification one of four; `quantity > 0`; remarks not blank |
| `items` | `(campus_id, name)` | `minimum_stock >= 0`; `item_kind` NULL or one of `RAW`, `PREPARED`, `OUTSOURCED` (`ck_item_kind`, migration `f3a8c2d61b47`) |
| `portion_standards` | `(campus_id, menu_id, item_id, version_no)` | status and source lists; `quantity_per_person > 0`; COPIED exactly when it references a menu main item; APPROVED exactly when approver, time, version (`>= 1`) and item kind (RAW or PREPARED) are set; CANCELLED exactly when the three cancellation fields are set |
| `portion_standard_basis` | `(standard_id, meal_record_id)` | `quantity_used > 0`; `people_served > 0` |
| `meal_plans` | `(campus_id, plan_seq)`; `(campus_id, plan_number)`; partial unique index `uq_meal_plan_session_date` on `(campus_id, plan_date, meal_session_id) WHERE status <> 'CANCELLED'` | status one of three; `expected_headcount >= 1`; approver and time together, required for APPROVED, absent for DRAFT (kept when an approved plan is cancelled); CANCELLED exactly when the three cancellation fields are set |
| `meal_plan_lines` | `(plan_id, item_id)` | an override has a quantity (`> 0`), a unit and a non-blank reason, or none of them; the eleven snapshot columns are all set or all empty; snapshot quantities and factor `> 0`, item kind RAW or PREPARED |
| `stock_adjustments` | `count_item_id` — one adjustment per count line; partial unique index `uq_stock_adjustment_pending_item` on `(campus_id, item_id) WHERE status = 'PENDING'` — one pending adjustment per item per campus; composite foreign keys `(count_item_id, count_id, item_id)` → `stock_count_items` and `(count_id, counted_by)` → `stock_counts` | `status IN (PENDING, APPROVED, REJECTED)`; PENDING exactly when `decided_at` and `decided_by` are empty; REJECTED needs a `decision_reason`; `decided_by <> counted_by` — the counter never decides |

Index for the ledger replay order: `ix_stock_movements_ledger_order` on
`stock_movements (campus_id, item_id, effective_at, id)`.

**Append-only ledger (migration M2b, decision 4b-5).** Two triggers on
`stock_movements` call `stock_movements_append_only()`, which raises an
error: `stock_movements_no_update_delete` (BEFORE UPDATE OR DELETE, for
each row) and `stock_movements_no_truncate` (BEFORE TRUNCATE, for each
statement). They fire for every role, superusers included; only an
explicit `ALTER TABLE … DISABLE TRIGGER` by the owner, or
`session_replication_role = replica`, bypasses them. Inserting is
allowed; corrections are REVERSAL rows.

**Final standards and plans (migration M4, safeguard S6-2).** Four row
triggers, for every role including superusers:
`portion_standards_final` (BEFORE UPDATE OR DELETE: a standard is never
deleted; an APPROVED or CANCELLED one never changes);
`portion_standard_basis_final` (BEFORE INSERT OR UPDATE OR DELETE: basis
rows are only added to a DRAFT standard and never changed or deleted);
`meal_plans_final` (BEFORE UPDATE OR DELETE: a plan is never deleted; a
CANCELLED plan never changes; an APPROVED plan may only become CANCELLED,
changing nothing but the status, cancellation fields and `updated_at`;
approval needs at least one line and every line's snapshot);
`meal_plan_lines_final` (BEFORE INSERT OR UPDATE OR DELETE: lines change
only while their plan is a DRAFT).

## 5. Rules enforced only in application code today

- Campus isolation of every query and every referenced record.
- Unit conversions must exist and match dimensions before purchases,
  receipts and menu standards are saved.
- A goods receipt may be accepted only once and only when accepted plus
  rejected quantities equal the received quantity.
- Receipt quantities may not exceed the purchased quantity.
- Only `ADMIN` can create users, assign staff permissions and permanently delete
  records. An `ADMIN` can create only `KITCHEN_MANAGER` and `STAFF` accounts,
  always in the `ADMIN`'s own campus.

### STAFF permission assignment

- STAFF users receive nothing by default. An `ADMIN` assigns individual
  permissions, chosen only from the staff-assignable list
  (`STAFF_ASSIGNABLE_PERMISSIONS` in `services/api/app/api/dependencies.py`):
  `dashboard.read`, `headcount.*`, `inventory.read`, `consumption.*`,
  `outsourced_food.*`, `menu.read` and `waste_tracking.*`. Any other
  permission is rejected (422), and the Staff Management page lists only
  assignable permissions.
- STAFF never receive `audit.read`, `menu.create` or `menu.update`; menus and
  portion standards stay read-only. No current code covers stock-adjustment
  approval.
- `inventory.create`, `inventory.update` and `purchase_order.*` are not
  assignable, because each also covers supplier writes, goods-receipt
  acceptance or supplier bills. They become assignable once split into
  separate codes.
- Older assignments outside the list are kept unchanged, and keep working,
  when an `ADMIN` saves a staff member's permissions. Removing them is a
  separate, approved cleanup.

### Kitchen Manager authority (confirmed 17 November 2026)

- `KITCHEN_MANAGER` holds every operational permission code, the same set
  `ADMIN` holds: master data, suppliers (create, edit, deactivate), supplier
  bills, recording and viewing supplier payments, and supplier balances
  (`purchase_order.*`), goods receipts, stock, menus, headcount, waste,
  dashboard and audit.
- Still `ADMIN`-only, enforced by role: creating users, managing staff
  permissions, permanently deleting any master record (stock items
  included) or waste record (403), and the dashboard's team overview.
- `STAFF` reaches bills, payments or balances only through an existing,
  active, explicit assignment (`purchase_order.read` to view,
  `purchase_order.create` to record). These codes are not in the assignable
  list, so only assignments made before that rule exist; they are honoured
  as stored and never changed by these features.
- Bill and payment entries in the dashboard activity feed are shown only to
  users who hold `purchase_order.read`.

### Supplier payments and balances (PUR04)

- There is no approval step. A recorded payment counts towards the bill's
  balance immediately; `supplier_payments` has no status or approver
  columns, and none are planned.
- Balances are derived, never stored: per bill, `grand_total` minus the sum
  of its payments. Each bill reports `outstanding` (unpaid part), `overpaid`
  (excess, which only data written outside the API can create) and a
  payment status: `UNPAID`, `PARTIALLY_PAID`, `PAID` or `OVERPAID`. A
  zero-total bill is `PAID`. Supplier totals add up `outstanding` and
  `overpaid` bill by bill, so one overpaid bill never hides another bill's
  unpaid amount.
- A payment's date cannot be later than today in the campus time zone
  (`APP_TIMEZONE`, default `Asia/Kolkata`; the server clock is UTC in Docker)
  or earlier than the bill's `purchase_date`. The dashboard's "today" and
  "this month" use the same campus date. Its amount cannot exceed the outstanding
  balance; a bill with nothing outstanding takes no payment (409).
- Every payment writes a `SUPPLIER_PAYMENT` audit row in the same
  transaction, with the bill, amount, date, method, reference and the
  balance before and after.
- Money in the bill, payment, balance and dashboard responses is a
  two-place decimal string ("1250.50").

### Bill attachments and duplicate invoices (PUR01, approved 18 November 2026)

- Attachments follow ADR-008. The database keeps metadata only (campus, bill,
  object key, original name, type, size, uploader, time, SHA-256). The file is
  kept in private storage, reached only through the API after the permission
  and campus checks. Development uses a local-disk adapter
  (`ATTACHMENT_STORAGE_DIR`, outside the repository). The production
  S3-compatible provider is not chosen (decision D9).
- Allowed files: PDF, JPEG, PNG and WEBP, recognised from the file's content;
  at most 10 MB each and 10 per bill. The same file cannot be attached to a
  bill twice. Object keys hold 128 random bits.
- Upload needs `purchase_order.create`; listing and downloading need
  `purchase_order.read`. Attachments are permanent: there is no delete or
  replace endpoint. Every upload is audited (`PURCHASE_ATTACHMENT`) in the
  same transaction as its row; if that fails, the stored file is removed.
- Exact duplicate invoices (same campus, supplier and number) are refused by
  the database. A **possible duplicate** is another bill from the same
  supplier whose number is equal once case, spaces and punctuation are
  ignored (NFKC, case-folded, letters, digits and combining marks kept). It is
  flagged, never blocked. A user with `purchase_order.update` may mark it
  "not a duplicate" with a note; only the review columns change, and the
  review is audited as an `UPDATE` of the `PURCHASE`.
- Bill transaction details (supplier, invoice, date, lines, totals) still
  have no edit or delete path.

### Purchase orders (Stage 3, decisions of 18 November 2026)

- Purchase orders are ADMIN and KITCHEN_MANAGER work: STAFF never pass a
  `purchase_order.*` check, whatever assignments exist (correction of
  20 November 2026; kept rows are history with no effect). Order
  information (order number, order-line links, ordered quantities) is
  left out of bill, receiving and activity responses for users without
  order access.
- Only DRAFT orders are edited; PLACED orders may be billed against, closed
  (with a reason) or, while no bill is linked, cancelled (with a reason).
  No approval step. Every change is audited (`PURCHASE_ORDER`).
- Order numbers are allocated under a lock on the campus row.
- A bill may be entered against a PLACED order of the same supplier and
  campus; its lines may link to the order's lines (same item). The order
  row is locked while the bill is saved. Billing more than was ordered is
  recorded and flagged on the order, never blocked.
- Progress per order line (billed, received, accepted, rejected, in draft
  receipts, left) is calculated from the linked bill lines and their goods
  receipts, converted into the order line's unit. Nothing is stored.

### Stock ledger (Stage 4 slice 4a, decisions of 23 November 2026)

- Balances are calculated from movements only: sum of direction × quantity,
  in the item's standard unit. Movements are replayed by `effective_at`,
  then `id`.
- Every posting that lowers stock locks the affected item rows in id order
  and is refused if the balance would be negative at any point from its
  effective time onwards (S2; interim until client question Q9).
- No endpoint edits or deletes a movement; a correction is a linked
  REVERSAL row effective at its posting time. Since migration M2b the
  database refuses UPDATE, DELETE and TRUNCATE too (section 4), and every
  application session refuses to flush a changed or deleted movement or to
  run a bulk UPDATE or DELETE on the table.
- Opening stock: ADMIN and KITCHEN_MANAGER only, dated today or earlier,
  effective at 00:00 campus time on that date; the entered quantity is
  converted through an explicit unit conversion and the factor is stored.
- Receipt acceptance posts RECEIPT movements effective at the acceptance
  time, with source key `RECEIPT_ITEM:<receipt line>`.

### Kitchen issues and unused returns (Stage 4 slice 4b, decisions of 23 November 2026)

- Drafts change no stock and may be saved when stock is short;
  confirmation posts one ISSUE (−1) or UNUSED_RETURN (+1) movement per line
  and is refused if a balance would go below zero at any point.
- Effective time: confirmation time when dated today, 23:59:59.999999
  campus time on the date when backdated; a return never before its issue.
- A return line gives back at most the issue line's quantity minus other
  confirmed or draft returns, checked under a lock on the issue.
- Reversal by ADMIN or KITCHEN_MANAGER only, whole document, with a reason;
  an issue with a confirmed return is reversed after the return.
- The menu must belong to the chosen meal session; both active and in the
  same campus.
- Locks are taken in one order: issue, return, campus (numbering), items.

### Stock counts and adjustments (Stage 4 slice 4c, decisions of 23 November 2026)

- Counts are blind: the count form receives no balance. When a count is
  saved the server locks the counted items, takes the count time and stores
  each line's system balance at that moment and the difference; a saved
  count is never changed (no endpoint, and every application session
  refuses to flush a changed or deleted count or count line).
- `stock_count.create` records counts and raises adjustment requests;
  `stock_count.read` views them; approving and rejecting are ADMIN and
  KITCHEN_MANAGER who did not perform the count (also a database check).
- Approval posts one ADJUSTMENT movement for the stored difference,
  effective at the count time (source `ADJUSTMENT:<id>`), through the S2
  check; rejection posts nothing.
- Raising and approving are refused once a movement dated on or before the
  count time was posted after the count (the stored difference would no
  longer reconcile the ledger); later-dated movements stay and follow the
  adjustment.
- Lock order: campus (numbering), then items; adjustment, then items.

### Meal records (Stage 5, decisions 5-1 to 5-10 of 23 November 2026)

- `meal.read` views, `meal.create` records, `meal.update` edits an OPEN record,
  closes it (only when it reconciles) and cancels it; a CLOSED or CANCELLED
  record refuses every change. Reopening (reason required) and the change
  history are ADMIN and KITCHEN_MANAGER only.
- Closing needs the actual counts and, for every dish, distributed and
  remaining recorded and leftovers adding up exactly to the remaining
  quantity; leftovers may be left unclassified while the record is OPEN.
- Retained food (interim, client question Q11): only from a CLOSED record,
  into a later OPEN record of the same campus, whole, as its own dish line
  with the same name and unit; the source line is locked while carried.
- Linked kitchen issues are derived from campus, date and meal session; a
  meal record never changes an issue, posts stock or creates a purchase,
  supplier return, credit or payment. The net usage per item at each
  closing is kept, and later changes are shown.
- Every action is an audit row (entity `MEAL_RECORD`), including each
  closing with a snapshot and each reopening with who, when and why.
- Lock order: meal records in id order (`FOR NO KEY UPDATE`).

### Meal planning (Stage 6, decisions 6-1 to 6-9 of 24 November 2026)

- Planning endpoints need the `ADMIN` or `KITCHEN_MANAGER` role and the
  `portion_standard.*` or `meal_plan.*` code; approving a standard or a plan,
  cancelling an approved plan and setting `items.item_kind` are role checks
  (`ADMIN`, `KITCHEN_MANAGER`). The item forms refuse `item_kind`, so no
  `inventory.*` grant classifies an item.
- A standard's or override's unit is the item's standard unit or has an
  explicit conversion record to it; weight-to-piece is never derived.
- Effective dates are today or later; an approved standard is replaced by
  approving a newer version (the latest effective date on or before the plan
  date wins, then the highest version). Copying menu main items creates
  drafts only; approval is separate for each.
- A DRAFT plan is calculated live (required = headcount × quantity per
  person; count units rounded up); approval writes each line's snapshot. An
  approved plan is corrected by cancelling it with a reason and creating a
  new one. Past-dated drafts can only be cancelled.
- Plans link to meal records only on the exact campus, date and
  `meal_session_id`; a record or plan in another session with the same name
  (ignoring letter case and extra spaces) is reported, never linked.
- Planning never writes stock movements, kitchen issues or returns, counts,
  adjustments, purchase orders, bills, receipts, supplier payments or
  supplier returns; it reads current stock balances and closed meal records.
- Every action is an audit row (entities `PORTION_STANDARD`, `MEAL_PLAN`;
  item-kind changes as `ITEM` `SET_KIND`).
- Lock order: plan or standard (`FOR NO KEY UPDATE`); version numbers under
  a key-share lock on the menu row; plan numbers through the campus lock.

### Outsourced food (Stage 8a, 24 November 2026; interim rules in `STAGE-8-IMPLEMENTATION-PLAN.md` §12)

- Orders are created, edited, placed and cancelled by `ADMIN` and
  `KITCHEN_MANAGER` (role and `outsourced_food.*` code); deliveries need
  `outsourced_food.create` (record) and `outsourced_food.update` (edit,
  confirm, cancel a draft); cancelling a confirmed delivery is a role check.
  Rates, totals, bill links and costs are returned only with
  `purchase_bill.read`; bill links need `purchase_bill.update`.
- Accepted quantities across an order line's draft and confirmed deliveries
  never exceed the ordered quantity (checked under the order lock).
- A confirmed delivery's accepted food becomes a received `meal_dishes` line
  on the OPEN record of the exact campus, date and `meal_session_id` — at
  confirmation, record creation or reopening; a CLOSED record is never
  changed (pending until reopened); cancelling a record releases its
  received lines.
- Outsourced items never enter stock: receipts, issues, opening stock,
  counts and `stock_ledger.post` refuse them; classification to OUTSOURCED is
  refused for items with stock movements, opening stock, counts or draft
  receipts and issues.
- No supplier return, credit or payable change is recorded for rejected
  food (Q6). Every action is an audit row (entities `OUTSOURCED_ORDER`,
  `OUTSOURCED_DELIVERY`, `MEAL_RECORD`, `OUTSOURCED_REPORT` exports).
- Lock order: delivery, order, meal session, meal record (`FOR NO KEY UPDATE`).

### Historical integrity

Rejected changes return 409. Historical records are never rewritten.

- A unit's dimension cannot change while the unit is referenced by items,
  unit conversions, purchase lines, menu standards, stock movements, waste
  lines, opening stock entries, kitchen issue and return lines, stock
  count lines, meal dishes, portion standards or meal plan lines.
- An item's standard unit cannot change while the item is referenced by
  purchase lines, goods receipt lines, stock movements, kitchen issue lines,
  stock count lines, menu standards, waste lines, portion standards or meal
  plan lines.
- A unit conversion can be edited or deleted only until it is used, that is
  until a purchase line, menu standard, portion standard or meal plan line
  converts between its two units. A used
  unit pair also cannot gain a second conversion in either direction.
  Conversions are not versioned yet, so a used factor cannot be corrected.
- Editing a master record applies the same validation as creating one.

## 6. Rules not yet enforced (planned)

- Purchase, receipt, payment and return `status` values are not constrained.
- Accepted receipts, opening stock, kitchen issues, unused returns, their
  reversals and approved count adjustments create stock movements; supplier
  returns do not yet (PUR05, client question Q6).
- Waste records do not change stock. Prepared-food waste must never change raw
  stock; raw-ingredient waste will post a stock movement once confirmation is
  introduced.
- Choosing the production attachment storage provider (D9); migration
  `e7b3c5a19d42` is applied to the development database.
- Payments are limited to the bill's outstanding balance, and reference
  numbers to one use per bill, in application code only (no database
  constraint). Payments are not tied to a bill status. They cannot be
  edited, voided or deleted yet; that needs a schema change.
- Supplier-return credits are not deducted from balances (client question
  Q6).
- No stock balance may go below zero: enforced by the application's posting
  check, not by a database constraint (client question Q9 still open).
- Plan-versus-actual for outsourced food (received quantities, PLAN08)
  waits for the outsourced-food stage.
- Prepared food has no master-data items yet (dish names are free text).

## 7. Staff access assignment flow (current)

1. `ADMIN` creates a user account in their own campus.
2. `ADMIN` opens Staff Management.
3. `ADMIN` selects individual actions from the staff-assignable permissions.
4. The system replaces the staff member's active assignable permissions, keeps
   any older non-assignable ones unchanged, and records an audit entry.
5. Staff signs in and sees only authorized pages and actions.
6. The backend validates every protected request.

The dashboard is calculated from operational tables. There are no duplicate
dashboard data tables.

## 8. Approved design changes not yet implemented

Summary only; nothing below exists in the database yet.

| Area | Planned change |
|---|---|
| Platform | `organizations` table; `campuses.organization_id`; one `SUPER_ADMIN` account with no campus |
| Accounts | Invitations, revocable refresh tokens, password reset, login throttling |
| Permissions | `role_permissions` table replacing the code-defined Kitchen Manager set; actions extended with `DELETE`, `APPROVE`, `EXPORT`, `RECORD` |
| Master data | Expiry flags; five canonical meal sessions via a session code. Built: item kind and versioned portion standards (Stage 6, `f3a8c2d61b47`) |
| Purchasing | `purchase_orders` with lines and an `ORDERED` state; `purchases` remains the supplier bill |
| Stock | Lots. Built: direction, source key, effective time and opening stock (slice 4a, `b5e1d7c3a920`); kitchen issues, unused returns and the append-only triggers (slice 4b, `c7d2e9f4a816`); physical counts and approved adjustments (slice 4c, `0e7d99065bd3`) |
| Food | Outsourced food. Built: meal records, prepared dishes, distribution, leftovers and interim carry-forward (Stage 5, `ea00e5387c2f`); meal plans with snapshots, overrides and plan versus actual (Stage 6, `f3a8c2d61b47`) |
| People | Staff attendance; hygiene and uniform checks; kitchen tasks (Pending, Completed, Postponed) |
| Insight | Alerts with recipients, actions and delivery history; supplier metrics; report exports |
| AI | Agent run, step and proposal tables (feature remains disabled) |

All future changes are additive Alembic migrations. Existing records,
migrations and primary key types are preserved.

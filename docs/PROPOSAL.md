# KITCHEN COPILOT

## Kitchen and Mess Management System with AI Agent

**Client:** Zaitoon International Girls Campus, Payyanur
**Project:** Kitchen and Mess Management System with Kitchen Copilot AI Agent
**Proposal Version:** 0.2
**Prepared Date:** 6 November 2026
**Status:** Approved
**Deployment Track:** Track A — AWS Free Tier (subject to eligibility and cost verification)

---

## 1. Executive Summary

Zaitoon International Girls Campus requires a centralized system to manage its daily kitchen and mess operations. These operations include purchasing ingredients, tracking supplier bills and payments, maintaining stock, recording daily ingredient usage, managing food preparation, tracking outsourced food, recording distribution and leftovers, and planning food quantities based on expected headcount.

Managing these activities through disconnected records and manual calculations can make it difficult to maintain accurate stock balances, trace expenses, identify purchase price changes and prepare the correct food quantities.

The proposed Kitchen Copilot is a web-based Kitchen and Mess Management System with an optional AI agent that supports operational decision-making.

The application will provide centralized management of:

- Purchases, supplier bills and payments.
- Stock receipts, kitchen issues, returns and adjustments.
- Daily meal sessions, preparation and food distribution.
- Outsourced food purchases and delivery records.
- Headcount-based food quantity planning.
- Purchase expenditure, price comparisons and operational reports.

An additional AI agent, Kitchen Copilot, will allow authorized users to ask questions in natural language, retrieve approved kitchen procedures, investigate live application data and prepare proposed actions for human review.

The core application will operate independently of AI. If the AI feature is disabled or unavailable, all standard operational workflows will remain usable.

The project will be developed in five proposed weekly releases, progressing from requirements and architecture to the complete application, AI integration, testing and handover.

## 2. Problem Statement and Proposed Solution

### 2.1 Existing Problem

Kitchen and mess operations involve several connected activities that require accurate records and calculations.

The main challenges addressed by this project are:

- Purchase quantities, unit prices and supplier expenses need centralized recording.
- Partial payments and outstanding supplier balances need to be tracked.
- Stock movements must be traceable from purchase receipt to kitchen usage.
- Physical stock differences must be investigated without overwriting historical records.
- Expected headcount and actual attendance-related food quantities must be recorded separately.
- Food preparation, distribution and leftovers must be reconciled.
- Outsourced food must be tracked separately from raw ingredients.
- Kitchen managers need reliable per-person quantity standards for meal planning.
- Management needs comparisons of purchase expenditure, quantities and unit prices over time.
- Staff need reliable reports instead of depending on disconnected records and manual calculations.

### 2.2 Proposed Solution

Kitchen Copilot will provide a centralized web application with role-based access and a consistent database for kitchen and mess operations.

The system will combine:

- A structured operational management application.
- A ledger-based inventory system.
- Headcount-based quantity planning.
- Financial and operational reporting.
- An optional AI-powered assistant with controlled application tools.

The application will be the source of truth for all operational records.

The AI agent will use approved procedures and authorized application tools to answer questions, investigate information and prepare proposals. It will not independently approve financial transactions or modify stock.

## 3. Project Objectives

The project aims to achieve the following objectives:

- Centralize kitchen purchases, expenses, suppliers and payment records.
- Maintain accurate stock balances using a traceable movement ledger.
- Record daily kitchen issues, unused returns and physical stock verification.
- Manage food preparation, distribution and leftovers.
- Track outsourced food quantities and costs separately.
- Calculate required food quantities using approved per-person standards and expected headcount.
- Compare planned quantities with actual usage and meal results.
- Provide purchase expenditure and unit-price comparison dashboards.
- Introduce AI-assisted operational investigation and planning.
- Maintain role-based access, audit history, data validation and backup procedures.
- Support desktop and mobile access for authorized campus staff.

## 4. Users and Role-Based Access

The application will support four roles.

### 4.1 User Roles

The following four-role access model and permission matrix were approved by the client on **05 November 2026**.

| Role | Responsibilities |
|---|---|
| Admin | Manage users, master data, suppliers, purchases, operational transactions, reports and eligible stock adjustments. |
| Kitchen Manager | Manage menus, items and portion standards; record operational transactions; approve meal plans and eligible stock adjustments; review reports and use Kitchen Copilot. |
| Store Keeper | Record accepted receipts, kitchen issues, unused returns and physical stock counts; view stock reports and ask stock-related Copilot questions. |
| Accounts | Manage suppliers, purchase bills, payments, supplier balances and financial reports; ask spending-related Copilot questions. |

### 4.2 Approved Permission Matrix

| Action | Admin | Kitchen Manager | Store Keeper | Accounts |
|---|---|---|---|---|
| Create and manage users | Yes | No | No | No |
| Manage categories and units | Yes | Yes | No | No |
| Manage items and menus | Yes | Yes | No | No |
| Manage portion standards | Yes | Yes | No | No |
| Manage suppliers | Yes | No | No | Yes |
| Record bills and payments | Yes | No | No | Yes |
| Record receipts | Yes | Yes | Yes | No |
| Record kitchen issues | Yes | Yes | Yes | No |
| Record unused returns | Yes | Yes | Yes | No |
| Record physical stock counts | Yes | Yes | Yes | No |
| Approve stock adjustments | Yes* | Yes* | No | No |
| Approve meal plans and standards | Yes | Yes | No | No |
| View financial reports | Yes | No | No | Yes |
| View stock reports | Yes | Yes | Yes | No |
| Use Kitchen Copilot | Yes | Yes | Stock-related | Spending-related |

An Admin or Kitchen Manager may approve a stock adjustment only if they did not perform the physical count.

Additional permissions for historical corrections, rate changes, cancellations and other sensitive operations will be defined before implementation.

### 4.3 Access Control Rules

- There will be no public registration.
- Only an Admin can create user accounts.
- Users cannot select or change their own roles.
- Every domain record will be associated with a campus.
- Every API query will enforce campus-level data isolation.
- Role and campus permissions will be checked on the backend, not only in the frontend.
- Rate changes, stock adjustments and historical corrections will be restricted to authorized users.
- All sensitive actions will be recorded in the audit history.
- Stock adjustment approval must follow the independent-counter rule.

## 5. Functional Requirements and User Stories

The following user stories preserve the original requirement IDs from the Zaitoon International Girls Campus Software Requirements Document v1.0.

Each requirement will be converted into implementation tasks and corresponding tests.

### 5.1 Purchases and Expenses

**PUR01 — Record Purchases and Bill Attachments**

User Story: As an Admin or Accounts user, I want to record supplier purchases with bill details and supporting documents so that every purchase is traceable.

Acceptance Criteria:

- The system must allow authorized users to record purchase date, supplier, invoice number, item, category, quantity, unit, unit rate, total and remarks.
- A bill may contain multiple item lines.
- Users must be able to attach bill images or documents.
- The system must identify possible duplicate supplier invoice numbers and flag them for review.
- Purchase records must preserve their original transaction details.

**PUR02 — Calculate Bill Totals**

User Story: As an Accounts user, I want purchase totals to be calculated consistently so that bill amounts remain accurate.

Acceptance Criteria:

- Item total = quantity × unit rate.
- Bill-level discounts and additional charges must be recorded separately.
- Bill total must include the recorded discounts and charges consistently.
- Actual purchase rates must remain available for historical comparisons.
- Monetary calculations must use exact decimal arithmetic.

**PUR03 — Record Accepted Receipts**

User Story: As a Store Keeper, I want to record physically accepted quantities separately from ordered or billed quantities so that only accepted goods enter stock.

Acceptance Criteria:

- Each receipt must be linked to its source purchase.
- Ordered, billed and accepted quantities must remain distinguishable.
- Only confirmed accepted quantities increase stock.
- Duplicate receipt posting must be prevented.
- Draft receipts must not affect stock.

**PUR04 — Track Supplier Payments and Balances**

User Story: As an Accounts user, I want to record full and partial supplier payments so that outstanding balances remain visible.

Acceptance Criteria:

- Payments must be linked to their corresponding bills.
- Each payment must include its date and amount.
- Outstanding balances must be recalculated after payment.
- Supplier-wise summaries must show purchases, payments and outstanding amounts.
- Purchase expenditure and cash payments must be reported separately.

**PUR05 — Record Supplier Returns and Credits**

User Story: As an Accounts or authorized operations user, I want to record supplier returns and related credits so that stock and payable records remain consistent.

Acceptance Criteria:

- Supplier returns must reference their original purchase.
- Related credit notes or adjustments must be traceable.
- Returned goods must be reflected in stock through appropriate movement records.
- Supplier credits must be reflected in payable calculations according to the approved accounting rule.
- Original purchase records must remain unchanged.

**Required Purchase Reports**

The system will provide:

**Monthly Chicken Purchase Summary**

- Number of purchase transactions.
- Number of distinct purchase days.
- Total kilograms purchased.
- Total purchase expenditure.

**Vegetable Purchase Report**

- Item name.
- Purchase date.
- Quantity.
- Unit.
- Unit rate.
- Total expense.

**Outsourced Breakfast Purchase Report**

- Food item.
- Supplier.
- Purchase date.
- Ordered and received quantities.
- Unit rate.
- Total cost.

The definition of a chicken purchase transaction must be confirmed with the kitchen manager, particularly when invoices contain multiple chicken lines or multiple receipts.

### 5.2 Stock and Daily Ingredient Usage

**STK01 — Opening Stock and Movement Ledger**

User Story: As a Store Keeper, I want to maintain opening stock and a complete movement ledger so that every stock balance can be explained.

Acceptance Criteria:

- Authorized users can record opening stock with an effective date.
- Opening stock must create a separate opening movement.
- The ledger must record receipts, kitchen issues, unused returns, supplier returns, approved adjustments and reversals.
- Every movement must contain its type, quantity, effective time and source reference.
- Posted movements must not be directly edited or deleted.

**STK02 — Record Kitchen Issues**

User Story: As a Store Keeper, I want to record ingredients issued to a kitchen session or dish so that daily ingredient usage is traceable.

Acceptance Criteria:

- Issues must contain date, meal session, dish or menu, item, quantity, unit, responsible user and remarks.
- Confirmed issues must reduce stock automatically.
- Draft issues must not change stock.
- Issues must be linked to the relevant kitchen or meal record.
- The application must prevent unsupported stock issues.

**STK03 — Record Unused Returns**

User Story: As a Store Keeper, I want to record unused ingredients returned from the kitchen so that net usage remains accurate.

Acceptance Criteria:

- Confirmed unused returns must increase stock.
- Issued quantity and returned quantity must remain separately visible.
- Net usage must be calculated as issued quantity minus unused returned quantity.
- Each return must reference its source issue.

**STK04 — Stock Balances and Low-Stock Alerts**

User Story: As a Store Keeper, I want to view stock balances and low-stock alerts so that shortages can be addressed.

Acceptance Criteria:

- Stock balances must be calculated from posted movement records.
- Items below their configured minimum stock level must be identified.
- A replenishment list must be available.
- Issues exceeding available stock must be prevented unless an authorized correction resolves the shortage.

**STK05 — Physical Stock Verification**

User Story: As a Store Keeper, I want to record physical counts and stock differences so that discrepancies can be investigated without overwriting history.

Acceptance Criteria:

- Stock counts must preserve the system balance at count time, physical quantity and difference.
- Verification date, verifier and reason must be recorded.
- The original count must remain unchanged.
- Any stock adjustment must be a separate movement.
- An authorized Admin or Kitchen Manager who did not perform the count must approve the adjustment.

**Stock Calculation Rule**

Stock balance = Opening stock + Receipts + Unused returns − Kitchen issues − Supplier returns ± Approved adjustments and reversals.

All quantities will be represented consistently using signed movement records.

### 5.3 Food Preparation and Distribution

**MEAL01 — Daily Meal Sessions and Headcounts**

User Story: As a Kitchen Manager, I want daily meal records for breakfast, lunch, snacks and dinner so that expected and actual headcounts can be compared.

Acceptance Criteria:

- Each meal session must be associated with a date.
- Expected student, staff and guest counts must be recorded separately.
- Actual people served must be recorded after the meal.
- Expected headcount and actual people served must remain separate.

**MEAL02 — Record Prepared Dishes**

User Story: As a Kitchen Manager, I want to record prepared dishes and output quantities so that preparation can be compared with ingredient usage.

Acceptance Criteria:

- Each prepared dish must have an output quantity and suitable unit.
- Preparation records must be linked to their meal sessions.
- Ingredient issues must be linked where applicable.
- Planned requirements and actual net ingredient usage must be comparable.

**MEAL03 — Record Food Distribution**

User Story: As a Kitchen Manager, I want to record available and distributed food quantities separately from headcount so that actual food quantities are not inferred from people counts.

Acceptance Criteria:

- Food item and available quantity must be recorded.
- Distributed quantity must be recorded separately.
- Remaining quantity must be recorded separately.
- Food quantities must use suitable units.
- People counts and food quantities must never be treated as interchangeable values.

**MEAL04 — Classify Leftovers**

User Story: As a Kitchen Manager, I want to classify remaining food so that retained, returned, wasted and disposed food is traceable.

Acceptance Criteria:

- Leftovers must be classified as retained, returned to supplier, wasted or otherwise disposed.
- Each classification must include quantity and relevant remarks.
- Retained food must remain traceable when carried forward.
- Retained food must not be recorded as a new purchase.

**MEAL05 — Reconcile Food Quantities**

User Story: As a Kitchen Manager, I want the application to validate food distribution and leftover quantities so that meal records remain consistent.

Acceptance Criteria:

- Available quantity = Distributed quantity + Remaining quantity.
- Leftover classifications must reconcile with the remaining quantity.
- The same quantity must not be counted twice.
- Invalid or inconsistent quantities must be rejected with a clear validation message.

### 5.4 Outsourced Food

**OUT01 — Track Outsourced Food Separately**

User Story: As an Accounts or Kitchen Manager user, I want ready-made food tracked separately from raw ingredients so that outsourced purchases and distribution remain traceable.

Acceptance Criteria:

- Record date, meal session, food item and supplier.
- Record ordered and received quantities separately.
- Record unit, unit rate and total cost.
- Record distributed and remaining quantities.
- Classify retained, returned, wasted and other disposal quantities.
- Link outsourced food costs to their source purchase records.
- Keep outsourced food separate from raw ingredient stock records.

**OUT02 — Outsourced Food Reports**

User Story: As an Admin or Accounts user, I want outsourced food reports by period, supplier, item and meal session so that quantities and expenditure can be reviewed.

Acceptance Criteria:

- Support daily, weekly, monthly and custom-date reports.
- Show received, distributed and leftover quantities.
- Display purchase expenditure.
- Allow filtering by item, supplier and meal session.

**OUT03 — Rejected Deliveries and Supplier Returns**

User Story: As an authorized user, I want rejected outsourced deliveries and supplier returns recorded separately so that purchase and stock records are not duplicated.

Acceptance Criteria:

- Rejected quantities must be recorded separately.
- Supplier returns must reference their source records.
- Purchase totals and stock records must not count the same transaction twice.
- Related credits or adjustments must remain traceable.

### 5.5 Headcount-Based Quantity Planning

**PLAN01 — Create a Meal Plan**

User Story: As a Kitchen Manager, I want to plan a meal using a menu and expected headcount so that selected main food quantities can be calculated.

Acceptance Criteria:

- Users must select a date, meal session, menu and expected headcount.
- Users must be able to select only the main items required.
- Entering every recipe ingredient must not be compulsory.

**PLAN02 — Define Per-Person Standards**

User Story: As an authorized Kitchen Manager or Admin, I want to define per-person quantity standards so that meal planning reflects approved campus portions.

Acceptance Criteria:

- Users can define per-person quantities for selected items.
- Items must be identified as raw ingredients or prepared food.
- Different menus may use different standards for the same ingredient.
- Standards must support weight-based and count-based quantities.

**PLAN03 — Suggest Standards from Historical Usage**

User Story: As a Kitchen Manager, I want suggested portion standards from historical usage so that future standards reflect actual consumption.

Acceptance Criteria:

- Suggested average per-person quantity = Total quantity used ÷ Total people served.
- Users must select relevant historical records.
- Calculations must use compatible units and valid records.
- Suggested standards must be presented for review.
- A responsible user must approve and save a suggested standard before it is applied.

**PLAN04 — Recalculate Quantities Immediately**

User Story: As a Kitchen Manager, I want quantities to recalculate whenever headcount or a standard changes so that meal plans remain accurate.

Acceptance Criteria:

- Required quantity = Expected headcount × Approved quantity per person.
- Recalculate immediately when headcount changes.
- Recalculate immediately when a standard changes.
- Support gram-to-kilogram display conversion.
- Round count-based food quantities up to whole pieces.
- Preserve the original standard and quantity used in saved historical plans.

**PLAN05 — Show Stock and Procurement Gap**

User Story: As a Kitchen Manager, I want to see required quantity, available stock and additional procurement quantity so that I can prepare purchase lists.

Acceptance Criteria:

- Additional procurement quantity = Maximum of (0, Required quantity − Available stock).
- Display required quantity.
- Display current available stock.
- Display additional quantity required.
- Clearly label future-plan stock figures as current availability, not forecasted availability.

**PLAN06 — One-Day Overrides and Versioned Standards**

User Story: As an authorized user, I want to apply temporary portion overrides and maintain standard versions so that exceptional plans do not rewrite historical information.

Acceptance Criteria:

- One-day overrides must include a reason.
- Overrides must apply only to the selected date and meal plan.
- New standards must support effective dates.
- Older plans must retain the standard values used when they were saved.
- Changes must be traceable through audit history.

**PLAN07 — Keep Planning Separate from Stock Transactions**

User Story: As a Kitchen Manager, I want meal plans to remain proposals so that planning cannot silently change inventory.

Acceptance Criteria:

- Creating a meal plan must not change stock.
- Editing a meal plan must not change stock.
- Only confirmed receipts, issues, returns and approved adjustments may change stock.

**PLAN08 — Compare Planned and Actual Results**

User Story: As a Kitchen Manager, I want to compare planned quantities with actual meal results so that portion standards can be improved.

Acceptance Criteria:

- Compare planned ingredient quantities with actual net usage.
- Compare planned and actual headcounts.
- Compare prepared or received food quantities.
- Show distributed and leftover quantities.
- Provide information for future portion-standard reviews.

### 5.6 Dashboard and Comparison Graphs

**DASH01 — Dashboard Indicators**

User Story: As an Admin or authorized report user, I want a filtered dashboard so that I can monitor purchase expenditure and price changes.

Acceptance Criteria:

- Support filters for date, month, category, item and supplier.
- Display total purchase expenditure.
- Display currency and percentage changes against the comparison period.
- Identify highest-spend categories.
- Identify items with the largest unit-price increases.
- Include monthly expenditure, category spending, item price trends, price increases and purchase quantity trends.

**DASH02 — Explain Price and Quantity Contributions**

User Story: As an Admin or Accounts user, I want current and previous period figures side by side so that expenditure changes can be understood.

Acceptance Criteria:

- Show current and previous purchase quantities.
- Show weighted average unit prices.
- Show total expenditure.
- Calculate changes in quantities, prices and expenditure.
- Separate the effects of price changes and quantity changes.
- Weighted average unit price = Total comparable item purchase value ÷ Total comparable quantity.
- Percentage change = ((Current value − Previous value) ÷ Previous value) × 100.
- If the previous value is zero or unavailable, display "Not comparable" instead of calculating a misleading percentage.

**DASH03 — Compare Like-for-Like Items**

User Story: As an Accounts user, I want item comparisons to use identical items and standard units so that price trends remain meaningful.

Acceptance Criteria:

- Compare the same item across selected periods.
- Convert quantities into the item's standard unit before comparison.
- Exclude incompatible records.
- Display returns, credits and bill-level charges separately unless an approved allocation rule exists.

**DASH04 — Compare Incomplete Months Fairly**

User Story: As an Accounts user, I want incomplete months compared using equivalent elapsed-day periods so that comparisons remain meaningful.

Acceptance Criteria:

- Compare the same elapsed-day ranges.
- Clearly display both comparison periods.
- Provide a separate full-month comparison option.

**DASH05 — Drill Down to Transactions**

User Story: As an authorized dashboard user, I want to inspect the transactions behind dashboard figures so that reported totals can be verified.

Acceptance Criteria:

- Selecting a graph point or total must open relevant source transactions.
- Display available bill attachments.
- Enforce the user's permissions when opening transaction details.

### 5.7 Master Data Management

The system will provide configurable master data for:

- Campuses.
- Categories.
- Units.
- Unit conversions.
- Items.
- Suppliers.
- Meal sessions.
- Menus.
- Menu main items.
- Portion standards.

Each item must include:

- Item name.
- Category.
- Item kind: raw, prepared or outsourced.
- Standard/base unit.
- Minimum stock level.
- Active/inactive status.

Categories must be configurable and may include rice, groceries, vegetables, chicken, fish, milk and outsourced food.

Unit conversion must use explicit conversion rules.

Search-as-you-type selection lists will be provided for frequently used items and suppliers.

### 5.8 Reports and Exports

The application will support daily, weekly, monthly and custom-date reports for:

- Purchase transactions.
- Category-wise expenses.
- Supplier balances.
- Outsourced food.
- Stock movements.
- Low-stock items.
- Daily ingredient usage.
- Physical stock differences.
- Food preparation and distribution.
- Leftovers.
- Planned versus actual quantities.
- Purchase quantity and price comparisons.

Every report must include its reporting period, filters, quantities and units.

**Export options:**

- Excel.
- PDF.
- Print-friendly view.

Purchase expenditure and supplier cash payments must be displayed separately.

Consumption costing is excluded until the campus approves a stock valuation method. If introduced later, it will be reported separately from purchase expenditure.

## 6. Daily Kitchen Operating Workflow

The application will support the following proposed daily operating sequence:

1. **Menu Confirmation:** The Kitchen Manager confirms the daily menu and meal session.
2. **Headcount Planning:** Expected student, staff and guest counts are recorded.
3. **Quantity Calculation:** The system calculates required quantities using approved per-person standards.
4. **Purchase and Receiving:** Required purchases are recorded and accepted deliveries are confirmed.
5. **Kitchen Operations:** Ingredients are issued to the kitchen, or outsourced food is received.
6. **Food Preparation:** Prepared dishes and actual output quantities are recorded.
7. **Distribution:** Available and distributed food quantities are recorded.
8. **Actual Headcount:** Actual people served are recorded.
9. **Leftover Reconciliation:** Remaining food is classified as retained, returned, wasted or otherwise disposed.
10. **Daily Review:** Kitchen managers review actual usage, stock balances, purchase expenditure and meal results.

This workflow connects purchases, inventory, meal planning and reporting through linked source records.

## 7. Kitchen Copilot — AI Agent Architecture and Capabilities

### 7.1 Overview

Kitchen Copilot will provide an optional AI assistant that allows authorized users to interact with kitchen data and approved procedures through natural language.

The agent will operate as an additional interface to the existing application. It will not replace the normal management screens or backend business rules.

The AI feature will be controlled through:

```env
AGENT_ENABLED=false
```

The default value will be false.

When disabled, the application must continue to support all normal operational workflows.

### 7.2 Three Core Agent Jobs

**Agent Job 1 — Plan and Procure**

Example request:

"Plan tomorrow's lunch biryani for 450 people and tell me what we need to buy."

Agent workflow:

1. Understand the user's request.
2. Retrieve approved menu standards and relevant kitchen procedures.
3. Call authorized application tools to calculate required quantities.
4. Check current stock balances.
5. Calculate additional procurement quantities using backend services.
6. Prepare a draft meal plan and purchase list.
7. Present calculations, evidence and source information to the user.

Expected Result:

A draft meal plan containing:

- Date and meal session.
- Expected headcount.
- Selected food items.
- Approved per-person standards.
- Required quantities.
- Current available stock.
- Additional procurement quantities.
- Supporting procedure references.

Approval Boundary:

The agent cannot independently save an approved meal plan or send a purchase request. Any eligible action must be reviewed and approved by the authorized user.

**Agent Job 2 — Explain Spending**

Example request:

"Why did food spending go up this month compared with last month?"

Agent workflow:

1. Understand the comparison period.
2. Check whether the current month is incomplete.
3. Retrieve purchase quantities, prices and expenditure through read-only tools.
4. Retrieve relevant headcount information.
5. Use tested application functions to calculate weighted average prices and expenditure changes.
6. Separate price contributions from quantity contributions.
7. Explain the important changes with supporting figures.
8. Provide links to relevant source transactions.

Expected Result:

An explanation showing:

- Previous-period expenditure.
- Current-period expenditure.
- Purchase quantity changes.
- Weighted average unit-price changes.
- Important contributing items and categories.
- Relevant headcount information.
- Source transaction references.

Approval Boundary:

This job is read-only and does not require transaction approval.

**Agent Job 3 — Investigate a Stock Difference**

Example request:

"Today's rice count is 12 kg below the system. Find out why and prepare an adjustment."

Agent workflow:

1. Retrieve the relevant physical stock count.
2. Read stock movements up to the count time.
3. Inspect relevant receipts, kitchen issues, unused returns and supplier returns.
4. Retrieve the approved stock verification procedure.
5. Investigate whether existing records explain the difference.
6. Present findings and supporting transaction references.
7. Prepare an adjustment proposal only when justified.

Expected Result:

A stock investigation report containing:

- Item and location/campus.
- System balance at count time.
- Physical count.
- Difference.
- Relevant stock movements.
- Possible explanations.
- Supporting evidence.
- Proposed adjustment quantity and reason, if justified.

Approval Boundary:

Only an authorized Admin or Kitchen Manager who did not perform the physical count may approve the adjustment.

The agent cannot approve or post stock adjustments independently.

### 7.3 AI Safety and Reliability

The following rules will govern all agent operations:

- **Application calculations are authoritative.** The model must not independently calculate authoritative stock balances, purchase totals, required quantities, average prices or percentage changes.
- **Controlled tools only.** The agent can access application data only through explicitly registered and permission-checked tools.
- **Campus isolation.** Every tool call must enforce the authenticated user's campus scope.
- **Role restrictions.** Tools must verify the user's permissions before accessing or proposing any operation.
- **Human approval.** Proposed actions remain drafts until approved by an authorized person.
- **No direct database access.** The LLM cannot directly connect to PostgreSQL, MongoDB or the Actions database.
- **Source-grounded retrieval.** Procedure-based answers must include their relevant source references.
- **No invented procedures.** If the approved documents do not contain the requested information, the agent must clearly state that the answer is unavailable from the approved sources.
- **Traceability.** Agent requests, tool calls, proposals, approvals and executions must be traceable.
- **Synthetic data.** Real supplier details, bills and staff information must not be sent to AI tools during development or demonstrations.
- **Network-independent testing.** A FakeLLM test path must demonstrate the agent workflow without requiring a live LLM connection.
- **AI-disabled operation.** All non-AI application workflows must continue to function when `AGENT_ENABLED=false`.

## 8. Technical Architecture

### 8.1 Technology Stack

| Component | Technology | Responsibility |
|---|---|---|
| Frontend | Next.js + TypeScript | User interface and application workflows |
| Main Backend | FastAPI | Authentication, APIs, domain services and agent orchestration |
| Operational Database | PostgreSQL | Main application records |
| Vector Search | pgvector | Procedure embeddings and semantic retrieval |
| Agent Trace Storage | MongoDB | Agent execution traces and related records |
| Background Processing | Celery | Asynchronous jobs |
| Message Broker/Cache | Redis | Celery broker and cache support |
| Action Executor | Flask | Executes validated and approved actions |
| Reverse Proxy | Nginx | Request routing and HTTPS entry point |
| Deployment | Docker Compose / AWS | Application packaging and hosting |

### 8.2 Architecture Responsibilities

**Frontend — `apps/web`**

- Login and authentication screens.
- Dashboard and reports.
- Purchase and supplier management.
- Stock and daily usage screens.
- Meal and outsourced food management.
- Quantity planning.
- Kitchen Copilot interface.
- Role-based navigation.

**Main API — `services/api`**

- Authentication and authorization.
- Campus-level access control.
- Master data APIs.
- Purchase and payment services.
- Stock ledger services.
- Meal and planning services.
- Reporting and export services.
- Agent orchestration.
- Controlled AI tools.
- Audit logging.
- Background task integration.

**Actions Service — `services/actions`**

- Receive validated action requests.
- Verify approval and authorization details.
- Execute permitted application actions.
- Prevent unauthorized or duplicate execution.
- Record execution results.
- Provide a health endpoint.

The Actions service will not accept direct execution requests from the LLM.

**Database Responsibilities**

**PostgreSQL**

The operational source of truth for:

- Users and roles.
- Campuses.
- Items and suppliers.
- Purchases and payments.
- Stock movements.
- Meal records.
- Portion standards.
- Meal plans.
- Reports and operational history.

**pgvector**

Stores embeddings for approved kitchen procedures and supports semantic retrieval.

**MongoDB**

Stores agent traces and related AI execution information.

**Actions Database**

Stores action proposals and execution records separately from the operational application database, following the Week 1 architecture decision.

### 8.3 Communication Flow

1. The user interacts with the Next.js application.
2. The frontend sends authenticated requests to FastAPI.
3. FastAPI validates identity, role and campus access.
4. For AI requests, FastAPI communicates with the configured LLM.
5. The LLM can request approved application tools.
6. FastAPI executes authorized tools using tested domain services.
7. Read-only results are returned to the agent for explanation.
8. Proposed write operations are stored as pending proposals.
9. An authorized human reviews and approves eligible actions.
10. The Actions service executes only validated, approved requests.
11. The application records the result and relevant audit information.

The frontend will never communicate directly with the LLM.

## 9. Data Architecture and Database Rules

### 9.1 Data Approach

PostgreSQL will be the primary source of truth for operational records.

The application will follow these rules:

- Every domain record must carry a `campus_id`.
- Every database query must enforce the authenticated user's campus scope.
- Stock balances must be derived from posted stock movement records.
- Stock-affecting transactions must be traceable to their source records.
- Posted stock movements must not be edited or deleted.
- Corrections must use linked reversals or approved adjustments.
- Bill files must be stored in object storage rather than database binary columns.
- Money must use Python `Decimal` and database numeric/decimal types.
- Quantities must use consistent base units.
- Unit conversions must be explicit and validated.
- Historical standards must be preserved in saved plans.
- Audit records must be written in the same database transaction as their corresponding changes.

### 9.2 Unit Management

Each item must have a standard/base unit.

Examples:

| Measurement Type | Base Unit |
|---|---|
| Weight | Gram |
| Volume | Millilitre |
| Count | Piece |

The application may display quantities in kilograms or litres where appropriate.

Conversions must use explicit `unit_conversions` records.

For example:

- 1 kg = 1,000 g.
- 1 litre = 1,000 ml.

Weight-to-piece conversion must never be assumed. It requires an approved item-specific conversion.

### 9.3 Money Management

- All monetary calculations will use exact decimal arithmetic.
- Use `Decimal` in Python.
- Use appropriate numeric/decimal database fields.
- Preserve two-decimal monetary precision for financial amounts.
- Avoid floating-point calculations for money.
- Store actual purchase rates for historical comparisons.
- Keep bill-level charges and discounts separately identifiable.

### 9.4 Stock Movement Ledger

Every stock movement will include:

- Campus.
- Item.
- Movement type.
- Signed quantity.
- Base unit.
- Effective timestamp.
- Source transaction reference.
- Responsible user.
- Creation timestamp.
- Reversal reference, where applicable.

Movement types:

- Opening.
- Receipt.
- Kitchen issue.
- Unused return.
- Supplier return.
- Approved adjustment.
- Reversal.

A unique source reference and database constraints will prevent duplicate posting.

Stock calculation:

Stock balance = Opening stock + Receipts + Unused returns − Kitchen issues − Supplier returns ± Approved adjustments and reversals.

### 9.5 Initial Database Areas

| Area | Proposed Tables |
|---|---|
| Master Data | campuses, categories, units, unit_conversions, items, suppliers, meal_sessions, menus, menu_items |
| Purchases | bills, bill_lines, bill_files, receipts, receipt_lines, payments, supplier_returns |
| Stock | stock_movements, kitchen_issues, stock_counts |
| Meals | meal_records, prepared_dishes, distributions, leftovers, outsourced_orders |
| Planning | portion_standards, meal_plans, meal_plan_lines |
| Authentication and Control | users, roles, audit_log |
| Agent Actions | action_proposals, action_executions in the Actions database |

The final ER diagram and normalized schema will be documented before implementation.

## 10. Synthetic Data and Initial Seed

Development, testing and demonstrations will use synthetic data.

The Week 1 seed plan proposes two demonstration campuses, approximately 60 items, eight suppliers, daily headcounts between 420 and 470, and three months of purchase and operational records.

These are demonstration targets, not confirmed campus production counts.

| Data Set | Proposed Seed Target |
|---|---|
| Campuses | 2 |
| Categories | 8–12 |
| Units | 5–10 |
| Unit conversions | 8–15 |
| Items | Approximately 60 |
| Suppliers | 8 |
| Meal sessions | 4 per campus |
| Menus | 8–12 per campus |
| Headcount records | 90 days per campus |
| Purchase bills | 3 months per campus |
| Receipts, issues and returns | Sufficient to demonstrate reconciliation |
| Payments | Full and partial payment examples |
| Supplier returns | Sample credit and return cases |
| Meal records | 90-day demonstration period |
| Stock counts | Reconciled and discrepancy examples |
| Demo users | One account per role per campus |
| Agent procedures | Two draft procedure pages for retrieval testing |
| Agent traces | Synthetic traces only |

The seed script will use a fixed random seed and deterministic record identification.

Running the seed script multiple times must not create duplicate records.

Synthetic purchase prices will include increases and decreases to support meaningful dashboard and AI demonstrations.

## 11. Scope and Priorities — MoSCoW

### 11.1 Must Have

The following capabilities are mandatory for the proposed v1.0 scope:

- All eight campus acceptance checks.
- Four-role authentication and authorization.
- Campus-level data isolation.
- Master data management.
- Purchase bills and attachments.
- Accepted purchase receipts.
- Supplier payments and returns.
- Stock movement ledger.
- Kitchen issues and unused returns.
- Physical counts and approved adjustments.
- Meal sessions and headcounts.
- Food preparation and distribution.
- Leftover management.
- Outsourced food tracking.
- Headcount-based quantity planning.
- Versioned portion standards.
- Plan-versus-actual comparison.
- Dashboard and required reports.
- Excel, PDF and print support.
- Audit history and validation.
- Duplicate transaction prevention.
- Backup and recovery procedure.
- All three Kitchen Copilot agent jobs.
- Approved procedure retrieval and controlled tools.
- Human approval boundaries.
- Traceable proposals and executions.
- AI-disabled application operation.
- Week 1 gate deliverables and five-week release sequence.

### 11.2 Should Have

No separate Should item is confirmed in the supplied requirements.

Tasks explicitly marked "if time allows" in the development plan may be scheduled after the Must scope, subject to sprint review and client agreement.

### 11.3 Could Have

No additional Could feature is committed in this proposal.

Any new feature must be reviewed and estimated before being added.

### 11.4 Won't Have in This Estimate

The following optional enhancements are excluded from the current estimate and may be quoted separately:

- Purchase request approvals.
- Expiry and batch tracking.
- Food arrival and taste-verification logs.
- Student attendance or leave integration for headcount.
- Integration with existing ERP or accounting software.

Consumption costing is also excluded until the campus approves a stock valuation method.

## 12. Deployment and Infrastructure

### 12.1 Selected Deployment Track

**Track A — AWS Free Tier**

AWS is the developer's proposed deployment choice.

The exact services, region, instance sizes, storage, networking, domain and TLS configuration will be finalized during technical estimation.

AWS Free Tier eligibility and usage limits must be checked in the actual AWS account before provisioning.

The proposal does not guarantee that every service or usage level will remain free.

Any charges beyond available Free Tier allowances must be monitored and reviewed.

### 12.2 Local Development

The project will support Docker Compose profiles:

- `core`
- `ai`
- `actions`

Nginx will start with the application stack.

The following command must start the core application:

```bash
docker compose --profile core up
```

The core services must provide appropriate health checks.

Required health endpoints:

- FastAPI: `/api/health`
- Flask Actions: `/health`

The AI agent will be disabled by default.

### 12.3 Development and CI

The project will include:

- Docker Compose configuration.
- Environment-variable templates without secrets.
- Database migrations using Alembic.
- Generated TypeScript API types from OpenAPI.
- Python linting and type checks.
- Frontend linting and type checks.
- Automated backend and frontend tests.
- CI validation for generated API types.
- GitHub pull requests and protected main branch.
- The agreed project repository structure.

```text
kitchen-copilot/
├── apps/
│   └── web/
├── services/
│   ├── api/
│   └── actions/
├── infra/
├── docs/
├── spikes/
└── scripts/
    └── seed.py
```

## 13. Security, Audit and Reliability

The application will implement the following supporting controls.

### Authentication and Security

- Cookie-based JWT authentication.
- Access and refresh token management.
- CSRF protection for cookie-authenticated unsafe requests.
- Role-based authorization.
- Campus-level access isolation.
- No public registration.
- Secure environment-variable handling.
- HTTPS through Nginx in production.

### Audit History

Audit records will capture:

- User responsible.
- Action performed.
- Record affected.
- Previous and new values where appropriate.
- Date and time.
- Approval information.
- Related source transaction.

Audit records must be written within the same transaction as the corresponding database change.

### Data Integrity

- Validate required fields and quantities.
- Validate units and conversions.
- Prevent duplicate receipt posting.
- Flag duplicate supplier invoice numbers.
- Preserve original stock counts.
- Correct posted stock entries through linked reversals or adjustments.
- Keep source transactions linked across modules.

### Backup and Recovery

The deployment will include an automated backup procedure and documented recovery steps.

Backup frequency, retention period, recovery-time objective and recovery-point objective must be confirmed with the campus before production handover.

### Device Support

The application will support desktop and mobile screens for operational entry and report viewing.

## 14. Handover Acceptance Tests

The following eight tests reproduce the campus acceptance checks in Section 12 of the Software Requirements Document v1.0.

All eight must pass before final handover.

### AT01 — Stock Movement Reconciliation

**Test:** Confirm a purchase receipt, issue ingredients to the kitchen and return unused ingredients.

Expected Result:

- Receipt increases stock exactly once.
- Kitchen issue decreases stock.
- Unused return restores stock.
- Ledger balance matches the displayed stock balance.

### AT02 — Physical Stock Verification

**Test:** Record a physical stock count that differs from the system balance.

Expected Result:

- Original system balance is preserved.
- Physical count and reason are recorded.
- Stock remains unchanged until an authorized adjustment is approved.
- Approver must not be the person who performed the count.

### AT03 — Monthly Chicken Purchase Report

**Test:** Generate a monthly chicken purchase report.

Expected Result:

- Transaction count is displayed.
- Distinct purchase days are displayed.
- Total kilograms are displayed.
- Total purchase expenditure is displayed.

### AT04 — Outsourced Breakfast Report

**Test:** Generate an outsourced breakfast report.

Expected Result:

- Received quantities are displayed.
- Distributed quantities are displayed.
- Leftover quantities are displayed.
- Quantities reconcile.
- Linked purchase cost is visible.

### AT05 — Headcount-Based Quantity Planning

**Test:** Plan biryani for 450 people using:

- Rice: 150 g per person.
- Chicken: 200 g per person.

Expected Result:

- Rice: 67.5 kg.
- Chicken: 90 kg.
- Changing headcount recalculates both quantities immediately.
- No stock movement occurs when the plan is created or edited.

### AT06 — Versioned Portion Standards

**Test:** Change a per-person standard and inspect an older saved plan.

Expected Result:

- New plans use the updated standard.
- Historical plans preserve their original standard and calculated quantity.
- Changes remain traceable.

### AT07 — Dashboard Comparison

**Test:** Compare periods with price and quantity changes, including zero or missing previous-period values.

Expected Result:

- Price contributions are distinguished from quantity contributions.
- Matching units are used.
- Weighted average prices are calculated correctly.
- Missing or zero comparison data displays "Not comparable" where a percentage cannot be calculated.
- Incomplete-month comparisons use matching elapsed-day ranges.

### AT08 — Supplier Payments and Export

**Test:** Record supplier payments and export a filtered report.

Expected Result:

- Full and partial payments reconcile with bill balances.
- Outstanding supplier amounts are correct.
- Filtered report totals match the on-screen totals.
- Excel and PDF exports preserve the selected filters and totals.

## 15. Week 1 Deliverables and Five-Week Release Plan

The project will follow the development sequence specified in the Week 1 module.

### Week 1 — Requirements, Design and Skeleton

**Release:** `v0.1`

Deliverables:

- Finalized `PROPOSAL.md`.
- Requirement-linked user stories.
- Client notes and open questions.
- ER diagram.
- Ledger and unit rules.
- Architecture Decision Records (ADRs) documenting the approved technical and data architecture decisions.
- Architecture diagram.
- Three working AI spikes:
  - LLM tool calling.
  - pgvector procedure retrieval.
  - Streaming responses.
- Repository structure and Docker Compose profiles.
- Health checks and CI.
- Cookie-based JWT authentication.
- Four user roles.
- Audit logging and role tests.
- Master data screens.
- Synthetic seed script.
- Sprint review and `v0.1` Git tag.

### Week 2 — Purchases, Stock and Approvals

**Release:** `v0.2`

Scope:

- PUR01–PUR05.
- STK01–STK05.
- Purchase and bill management.
- Receipt posting.
- Supplier payments and returns.
- Stock movement ledger.
- Kitchen issues and unused returns.
- Physical stock verification.
- Stock adjustment approval.
- Related validation and audit tests.

### Week 3 — Meals, Outsourced Food, Planning and Dashboard

**Release:** `v0.3`

Scope:

- MEAL01–MEAL05.
- OUT01–OUT03.
- PLAN01–PLAN08.
- DASH01–DASH05.
- Required reports and exports.
- Meal preparation and distribution.
- Leftover reconciliation.
- Headcount-based planning.
- Planned-versus-actual comparisons.

### Week 4 — Kitchen Copilot AI Agent

**Release:** `v0.4`

Scope:

- Three agent jobs.
- Approved procedure retrieval.
- pgvector integration.
- LLM tool calling.
- Controlled application tools.
- Streaming responses.
- Action proposal workflow.
- Approval boundaries.
- Flask Action Executor integration.
- FakeLLM testing.
- Agent guardrails and evaluation.

### Week 5 — Hardening, Handover and Demo Day

**Release:** `v1.0`

Scope:

- Security and permission review.
- Data integrity testing.
- Performance and reliability checks.
- Backup and recovery verification.
- Complete acceptance testing.
- Excel/PDF export validation.
- AI evaluation and safety verification.
- Deployment.
- Documentation.
- User training.
- Final demonstration and handover.

### 15.1 Delivery Assumptions

The five-week roadmap represents the proposed development sequence and target releases.

Actual delivery depends on:

- Client feedback and approval.
- Confirmation of unresolved business rules.
- Availability of development resources.
- Infrastructure provisioning.
- Historical data availability.
- Successful testing and acceptance results.

Any additional requirements identified during development will be reviewed for their effect on scope, cost and delivery time.

Production handover will proceed after the agreed acceptance checks have been demonstrated and outstanding client dependencies have been resolved.

## 16. Risks and Mitigation

| Risk | Impact | Proposed Mitigation |
|---|---|---|
| Incorrect unit conversions | Inaccurate stock balances | Explicit conversion rules and automated tests |
| Duplicate receipt posting | Inflated inventory | Unique source references and idempotency |
| Editing posted movements | Loss of audit history | Immutable movements and linked reversals |
| Inconsistent bill-level charge allocation | Misleading price comparisons | Keep charges separate until an allocation rule is approved |
| Incomplete-month comparisons | Misleading financial analysis | Compare equivalent elapsed-day periods |
| Incorrect historical standards | Inaccurate historical plans | Effective-dated standard versions and saved snapshots |
| Unauthorized stock adjustments | Inventory discrepancies | Role checks and independent approval |
| AI-generated incorrect proposals | Operational mistakes | Tested calculations, evidence and human approval |
| AI service unavailable | Loss of AI functionality | AI-disabled core application remains operational |
| AWS usage beyond Free Tier | Unexpected hosting charges | Monitor costs and verify eligibility before deployment |
| Data loss | Operational disruption | Automated backups and tested recovery |

## 17. Assumptions and Open Client Questions

The following assumptions must be validated before the related implementation decisions are finalized.

### 17.1 Current Assumptions

- The four-role access model and permission matrix were approved by the client on 05 November 2026.
- PostgreSQL is the operational source of truth.
- MongoDB stores agent traces.
- The Actions service maintains its own action proposal and execution records.
- Development and demonstration environments use synthetic data.
- Consumption costing is excluded until a stock valuation method is agreed.
- AWS is the intended deployment track, subject to eligibility and cost review.
- Historical standards will be preserved in saved meal plans.

### 17.2 Open Questions for the Kitchen Manager and Campus

1. How many campuses and physical stores must the production application support at launch?
2. Who may create or edit each master-data type?
3. Who approves new portion standards and menus?
4. What exactly counts as one chicken purchase transaction when an invoice contains multiple chicken lines or multiple receipts?
5. How should bill-level discounts and extra charges be allocated across purchase item lines, if allocation is required?
6. How should supplier credits, rejected deliveries and outsourced-food returns affect payable balances and reports?
7. Which units and item-specific conversions are used in daily kitchen operations?
8. Are any weight-to-piece conversions officially approved?
9. What is the policy for negative stock and emergency kitchen issues?
10. What operational fallback should apply when no eligible independent approver is available?
11. What is the approved process for retained leftovers carried into another meal or day?
12. Which historical records and bill attachments must be imported?
13. Who will validate imported historical data?
14. What are the required data-retention period, backup frequency, recovery-time objective and recovery-point objective?
15. How many concurrent users are expected?
16. What performance and availability targets are required?
17. Which AWS region and hosting services are approved?
18. What monthly hosting cost ceiling applies after Free Tier allowances?
19. What login/session duration and account recovery policies are required?
20. Who may use each AI agent job?
21. Which kitchen procedures are approved for AI retrieval?
22. What approval process is required before an AI-generated purchase or stock adjustment proposal can be executed?

All answers will be documented in:

`docs/client-notes.md`

Unresolved questions must not be treated as approved business rules.

## 18. Delivery, Estimation and Handover

The proposed five-week development plan will be used as the initial delivery roadmap.

Before production handover, the following commercial and operational details must be confirmed:

- Module-wise development cost.
- Delivery timeline and milestones.
- Hosting and recurring infrastructure charges.
- Support and maintenance terms.
- User training arrangements.
- Initial data entry and historical-data import arrangements.
- User capacity and performance targets.
- Backup and recovery requirements.
- Data retention requirements.
- Excluded and optional enhancements.

### 18.1 Handover Deliverables

The final handover package will include:

- Application source code.
- Frontend and backend documentation.
- Deployment configuration.
- Environment-variable template without secrets.
- Database migration instructions.
- Synthetic seed instructions.
- Backup and recovery procedure.
- Role and user guide.
- API documentation.
- Test results and acceptance evidence.
- AI usage and evaluation record.
- Demonstration of all eight acceptance checks.
- Deployment and operational instructions.

## 19. Proposal Approval

**Proposal:** Kitchen Copilot — Kitchen and Mess Management System with AI Agent
**Client:** Zaitoon International Girls Campus, Payyanur
**Proposal Version:** 0.2
**Status:** Approved

The proposal scope and four-role permission matrix were approved by the client on **05 November 2026**. Remaining operational questions listed in Section 17.2 are still open and must be resolved before the related features are finalized.

| Approval | Details |
|---|---|
| Prepared by | Development Team |
| Reviewed by | Kitchen Manager |
| Approved by | Campus Management |
| Approval Date | 05 November 2026 |
| Final Scope Confirmation | Approved — proposal scope; operational questions remain |

### Important Note

This proposal is based on the supplied Week 1 development module and the Zaitoon International Girls Campus Software Requirements Document v1.0 dated 6 November 2026.

The original requirement IDs and eight campus acceptance checks have been retained.

All unresolved operational rules are intentionally listed for client confirmation before implementation.

**Document Status: Approved by Client.**

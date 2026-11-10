
# Kitchen Copilot — Requirements Traceability

Source: Campus Software Requirements Document (SRD) v1.0

Status: Week 1 implementation tracking — requirement-level progress recorded from verified implementation and test evidence.

## 1. Purchase and Supplier Management

| ID | Requirement | Status |
|---|---|---|
| PUR01 | Purchase management | IN_PROGRESS |
| PUR02 | Supplier bill management | IN_PROGRESS |
| PUR03 | Goods receipt management | IN_PROGRESS |
| PUR04 | Supplier payment management | PENDING |
| PUR05 | Supplier returns and credits | PENDING |

## 2. Stock and Inventory Management

| ID | Requirement | Status |
|---|---|---|
| STK01 | Opening stock and stock ledger | IN_PROGRESS |
| STK02 | Kitchen stock issues | PENDING |
| STK03 | Unused stock returns | PENDING |
| STK04 | Stock balances and low-stock monitoring | PENDING |
| STK05 | Physical stock counts and adjustments | PENDING |

## 3. Meal Preparation and Distribution

| ID | Requirement | Status |
|---|---|---|
| MEAL01 | Student headcount records | IN_PROGRESS |
| MEAL02 | Food preparation records | PENDING |
| MEAL03 | Food distribution records | PENDING |
| MEAL04 | Leftover tracking | PENDING |
| MEAL05 | Meal quantity reconciliation | PENDING |

## 4. Outsourced Food Management

| ID | Requirement | Status |
|---|---|---|
| OUT01 | Outsourced food tracking | PENDING |
| OUT02 | Outsourced food reporting | PENDING |
| OUT03 | Rejected deliveries and supplier returns | PENDING |

## 5. Quantity Planning

| ID | Requirement | Status |
|---|---|---|
| PLAN01 | Headcount-based meal planning | PENDING |
| PLAN02 | Per-person ingredient standards | PENDING |
| PLAN03 | Historical planning suggestions | PENDING |
| PLAN04 | Automatic quantity recalculation | PENDING |
| PLAN05 | Procurement gap calculation | PENDING |
| PLAN06 | Manual overrides and versioning | PENDING |
| PLAN07 | Planning separate from actual stock | PENDING |
| PLAN08 | Planned-versus-actual comparison | PENDING |

## 6. Dashboard and Reports

| ID | Requirement | Status |
|---|---|---|
| DASH01 | Dashboard filters | PENDING |
| DASH02 | Price and quantity decomposition | PENDING |
| DASH03 | Like-for-like unit comparison | PENDING |
| DASH04 | Partial-month comparison | PENDING |
| DASH05 | Report drilldown | PENDING |

## 7. Cross-Cutting Requirements

| Area | Requirement | Status |
|---|---|---|
| Authentication | Secure login and session management | TESTED |
| Authorisation | Four roles and permissions | IN_PROGRESS |
| Campus isolation | Campus-scoped data access | TESTED |
| Audit | Record important user activities | IN_PROGRESS |
| Reports | Export and print support | PENDING |
| AI | Controlled agent and approval workflows | IN_PROGRESS |
| Security | Protect sensitive operational information | IN_PROGRESS |

## 8. Acceptance Tests

| ID | Acceptance scenario | Status |
|---|---|---|
| AT01 | Stock movements and balance reconciliation | PENDING |
| AT02 | Physical count and approved adjustment | PENDING |
| AT03 | Monthly purchase reporting | PENDING |
| AT04 | Outsourced food reconciliation | PENDING |
| AT05 | Headcount-based quantity calculation | PENDING |
| AT06 | Historical standard preservation | PENDING |
| AT07 | Price and quantity comparison | PENDING |
| AT08 | Supplier payment reconciliation and exports | PENDING |

## 9. Status Definitions

- PENDING: No verified implementation of the requirement yet.
- IN_PROGRESS: Some implementation exists, but the complete requirement is not finished.
- IMPLEMENTED: The complete requirement has been implemented.
- TESTED: The implemented requirement has passed its relevant verification tests.
- ACCEPTED: The delivered requirement has been confirmed by the client.

A requirement must not be marked IMPLEMENTED or TESTED without supporting evidence. ACCEPTED requires client confirmation.

Approval of the project proposal and permission matrix on 05 November 2026 does not automatically mean individual requirements have been implemented, tested, or accepted.

The Week 1 development milestone does not represent completion or production acceptance of the entire Kitchen Copilot system.

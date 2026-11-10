# Kitchen Copilot — Client Notes and Confirmed Decisions

## Approval Record

- Proposal: Kitchen Copilot — Kitchen and Mess Management System with AI Agent
- Client: Zaitoon International Girls Campus, Payyanur
- Proposal version: 0.2
- Approval date: 05 November 2026
- Status: Approved by Client

## 1. Approved User Roles and Permissions

The client approved the four-role permission matrix.

| Role | Approved responsibilities |
|---|---|
| Admin | Manage users, master data, suppliers, purchases, operational transactions and eligible approvals. |
| Kitchen Manager | Manage menus, items and portion standards; record operational transactions; approve meal plans and eligible stock adjustments. |
| Store Keeper | Record accepted receipts, kitchen issues, unused returns and physical stock counts; view stock reports. |
| Accounts | Manage suppliers, purchase bills, payments, supplier balances and financial reports. |

## 2. Confirmed Access Rules

- Public registration is not allowed.
- Only Admin can create user accounts.
- Users cannot select or change their own roles.
- Every domain record must be associated with a campus.
- Backend authorization must enforce role permissions and campus isolation.
- Sensitive operations must be recorded in audit history.

## 3. Stock Adjustment Approval

- Admin and Kitchen Manager may approve stock adjustments.
- The approver must not be the person who performed the physical count.
- Store Keepers can record physical stock counts but cannot approve stock adjustments.
- The operational fallback when no eligible independent approver is available remains unresolved.

## 4. Supplier Permissions

- Admin and Accounts can manage supplier records.
- Other supplier permissions remain subject to the approved permission matrix.

## 5. Outstanding Clarifications

The following topics are not confirmed by the current approval record and must not be treated as approved business rules:

- Number of production campuses and physical stores.
- Store transfers and negative-stock policy.
- Emergency stock issue procedure.
- Unit requirements and item-specific conversions.
- Purchase discounts, extra charges and supplier credits.
- Purchase approval and supplier payment approval workflow.
- Meal headcount collection and historical standards.
- Leftover handling and outsourced-food procedures.
- Reports, exports and historical data retention.
- AI access, approved knowledge sources and action approval.
- Hosting budget, AWS services, backups and recovery objectives.
- Login/session duration and account recovery.
- Performance and availability targets.

Refer to `docs/CLIENT-QUESTIONS.md` for the clarification register.

## 6. Documentation Rule

Only decisions explicitly confirmed by the client may be recorded as approved. Unanswered questions remain open until confirmed.

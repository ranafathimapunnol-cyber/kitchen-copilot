# Kitchen Copilot — Client Clarification Questions

Status: Partially answered — approved role decisions are recorded in docs/client-notes.md; remaining questions require client confirmation.

## 1. Campus and Stores

1. How many campuses will use the system?
2. Does each campus have one store or multiple stores?
3. Can stock be transferred between stores?

## 2. User Roles

Confirmed by the approved permission matrix:

- Kitchen Managers may approve stock adjustments only if they did not perform the physical count.
- Store Keepers may record physical stock counts but cannot approve stock adjustments.
- Admin and Accounts may manage supplier records.

Still awaiting clarification:

1. Who approves purchases?
2. Who approves supplier payments?

## 3. Inventory

1. Should negative stock be allowed?
2. How should emergency stock issues be recorded?
3. Which units are required for each inventory item?
4. How should physical stock differences be handled?

## 4. Purchases and Accounts

1. How are bill discounts and additional charges calculated?
2. How are supplier credits recorded?
3. Can a purchase have multiple receipts?
4. How are partial supplier payments handled?

## 5. Meal Planning

1. How is daily student headcount collected?
2. Who can change ingredient standards?
3. Can the same menu have different standards on different days?
4. Should leftovers be carried forward to the next day?

## 6. Outsourced Food

1. Which meals are usually outsourced?
2. Who confirms received quantities?
3. How are rejected deliveries recorded?

## 7. Reports

1. Which reports are required by Accounts?
2. Which reports are required by Kitchen Managers?
3. Are Excel and PDF exports both required?
4. What historical period must be retained?

## 8. AI Agent

1. Which staff members can use the AI assistant?
2. Which operational procedures can be used as AI knowledge sources?
3. Which actions require human approval?
4. Is external LLM API usage permitted?

## 9. Deployment

1. What is the approved hosting budget?
2. Is AWS the required hosting platform?
3. What are the backup and recovery requirements?

Only explicitly confirmed decisions are recorded as approved. Remaining questions must be reviewed with the client before finalising the relevant system behaviour. Confirmed role decisions are documented in docs/client-notes.md.

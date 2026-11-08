# Ledger and Unit Rules

## Stock ledger

1. Calculate balances from posted stock movements.
2. Every movement belongs to a campus and references its source transaction.
3. Posted movements are immutable.
4. Correct errors through reversals or approved adjustments.
5. Prevent duplicate posting using unique source references.
6. Receipt acceptance posts only accepted quantities.
7. Movement types include opening stock, receipt, kitchen issue, unused return, supplier return, approved adjustment and reversal.
8. Enforce campus scope on all stock queries.

## Units

1. Use a consistent base unit for each item.
2. Examples: gram, millilitre and piece.
3. Conversions must be explicit and dimension-compatible.
4. Never assume weight-to-piece conversion.
5. Preserve historical conversion factors.
6. Same-unit conversion factor is 1.
7. Reject missing or incompatible conversions.

## Financial rules

1. Use decimal precision, never floating-point money.
2. Monetary values use two decimal places.
3. Preserve transaction-time prices.
4. Calculate totals from validated lines and discounts.
5. Audit financial changes.

## Approval and audit

Record actor, campus, action, entity, timestamp and relevant change details. A person must not approve an adjustment for a count they performed. Define historical correction, cancellation and rate-change rules before implementing them.

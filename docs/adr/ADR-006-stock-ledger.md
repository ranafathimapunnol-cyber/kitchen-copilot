# ADR-006: Immutable Stock Ledger

- Status: Accepted
- Date: 2026-11-08

## Context

The system needs accurate, campus-scoped stock balances and a traceable history of stock changes. Editing a stored balance directly makes it difficult to explain or audit how stock changed.

## Decision

Use an append-only stock movement ledger as the authoritative record of stock changes.

Stock balances are derived from posted movements rather than maintained as independently editable quantities.

Supported movement categories include:
- Opening stock
- Accepted purchase receipt
- Kitchen issue
- Unused kitchen return
- Supplier return
- Stock adjustment
- Reversal

Corrections must use compensating or reversal movements. Existing posted movements must not be silently overwritten or deleted.

Each movement records its campus, item, quantity, unit, movement type, reference, actor and timestamp.

## Transaction and integrity rules

- A movement must belong to the same campus as its referenced records.
- A purchase receipt creates stock only for accepted quantities.
- Receipt acceptance and corresponding stock movements must be committed atomically.
- Duplicate receipt posting must be prevented.
- Reversal movements must reference the original movement.

## Consequences

- Stock history is traceable.
- Balances can be reconstructed from ledger entries.
- Corrections require explicit reversal records.
- Queries may need aggregation or cached projections as data grows.

# ADR-007: Units and Conversion Rules

- Status: Accepted
- Date: 2026-11-08

## Context

Purchases, receipts, menus and stock operations may express the same item in different units. Uncontrolled conversions can create incorrect stock quantities.

## Decision

Every item has a standard stock unit. Quantities in operational records must include their unit.

Conversions are explicit, campus-scoped records between compatible unit dimensions. A conversion factor defines how many target units correspond to one source unit.

The application must reject:
- Conversions between incompatible dimensions.
- Missing conversion factors when a conversion is required.
- Zero or negative conversion factors.
- Cross-campus unit or conversion references.

A same-unit conversion has a factor of one.

## Numeric precision

- Money uses Decimal arithmetic and two decimal places for stored totals.
- Unit conversion factors use fixed decimal precision.
- Quantities use three decimal places unless a specific domain rule requires otherwise.
- Binary floating-point arithmetic must not be used for financial calculations.

## Consequences

- Stock quantities can be normalized to an item's standard unit.
- Conversion rules are explicit and testable.
- Users must configure valid conversions before using incompatible units together.

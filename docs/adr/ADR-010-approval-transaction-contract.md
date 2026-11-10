# ADR-010: Approval and Transaction Contract

- Status: Accepted
- Date: 2026-11-08

## Context

Operational actions may affect purchases, stock, payments and other important campus records. An approval must not bypass role permissions, campus isolation, validation or audit logging.

AI-generated suggestions must never directly approve or execute business actions.

## Decision

All business mutations and approval decisions must be enforced by the server through validated application services.

Every protected operation must establish:
- The authenticated actor.
- The actor's role and campus scope.
- The target record and its current state.
- The permission required for the requested transition.
- The business validation rules and preconditions.

Only an authorized human actor may make an approval decision. AI may prepare a recommendation or proposed action but cannot grant its own approval.

## Atomic transaction contract

For a database-backed approval or protected mutation:

1. Load and validate the target record within the actor's campus.
2. Check the actor's permission and the allowed state transition.
3. Apply the business state change.
4. Write the corresponding audit record with actor, campus, action, entity, timestamp and relevant change details.
5. Commit the state change and audit record in the same database transaction.

If validation, mutation or audit creation fails, the transaction must roll back.

Retries must not create duplicate business effects. Use idempotency controls where operations may be retried.

External side effects, such as notifications, must happen after the database transaction commits and must not be used as a substitute for the authoritative audit record.

## Consequences

- Unauthorized state transitions are rejected server-side.
- Business changes and their audit records remain consistent.
- Failed operations do not leave partially committed database changes.
- Approval and audit behavior can be tested independently of AI components.
- Specific role permissions and approval thresholds remain governed by the approved permission matrix and business requirements.

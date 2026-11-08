# ADR-004: Background Processing

- Status: Accepted
- Date: 2026-11-08

## Context
Long-running AI and application tasks should not block API requests.

## Decision
Use Redis and Celery for background processing.

## Consequences
- Tasks can run asynchronously.
- Tasks must be safe to retry.
- Duplicate side effects must be prevented.

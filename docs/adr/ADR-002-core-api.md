# ADR-002: FastAPI Core API

- Status: Accepted
- Date: 2026-11-08

## Context
The system requires authentication, authorization, campus isolation and AI orchestration.

## Decision
Use FastAPI as the main application API.

## Consequences
- Centralized authentication and authorization.
- Campus-scoped data access.
- Validated API requests and audit logging.

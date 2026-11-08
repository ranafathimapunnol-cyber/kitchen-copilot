# ADR-005: Separate Actions Service

- Status: Accepted
- Date: 2026-11-08

## Context
AI-assisted operations must not bypass validation, authorization or audit controls.

## Decision
Use a separate Flask Actions service for approved operational actions.

## Consequences
- Validate every action before execution.
- Never execute arbitrary LLM-generated database commands.
- Enforce campus scope and authorization.
- Provide a health endpoint and audit trail.

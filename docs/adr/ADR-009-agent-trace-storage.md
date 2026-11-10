# ADR-009: Document Storage for AI Agent Traces

- Status: Accepted
- Date: 2026-11-08

## Context

AI agent traces may contain variable document structures such as prompts, model responses, tool-call inputs, tool results, execution metadata and error details.

These records have a different access and consistency pattern from core business transactions.

## Decision

Use MongoDB for document-oriented AI execution traces when the agent-tracing workload is enabled.

PostgreSQL remains authoritative for:
- Users and permissions
- Campus records
- Purchases and payments
- Stock movements
- Approval decisions
- Business audit logs

MongoDB trace documents are supporting diagnostic records. They must never be treated as proof that a business action was authorized or successfully committed.

Each trace should include appropriate correlation identifiers, such as campus ID, actor ID, request ID and execution ID. Sensitive credentials, authentication tokens and unnecessary personal data must not be recorded.

## Why not store every trace in PostgreSQL?

PostgreSQL JSONB can store flexible trace documents and remains a valid option for low-volume workloads.

MongoDB is selected for the target document-oriented trace workload because trace structures can vary between agent versions and execution types, and traces may be queried independently from transactional records.

This choice does not justify duplicating authoritative business data in MongoDB.

## Consequences

- Business transactions remain in PostgreSQL.
- Agent trace documents can evolve independently.
- Trace storage requires separate access controls, retention and backup policies.
- MongoDB deployment and integration are not prerequisites for the current core application.
- If trace volume remains small, PostgreSQL JSONB may be simpler and should be reconsidered before operating an additional database.

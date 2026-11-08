# ADR-003: Data Storage

- Status: Accepted
- Date: 2026-11-08

## Context
The application needs reliable transactional records and semantic procedure retrieval.

## Decision
Use PostgreSQL for transactional data, pgvector for semantic retrieval and MongoDB for approved document-oriented use cases.

## Consequences
- PostgreSQL remains authoritative for stock and financial transactions.
- Vector retrieval does not replace transactional records.
- Campus isolation applies to supporting data stores.

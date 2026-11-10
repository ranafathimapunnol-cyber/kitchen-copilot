# ADR-008: Purchase Bill Attachment Storage

- Status: Accepted
- Date: 2026-11-08

## Context

Purchase bills may contain scanned invoices, photographs or PDF documents. Storing binary files directly in transactional database rows increases database size and complicates backup and file delivery.

## Decision

Use private S3-compatible object storage for purchase bill attachments.

PostgreSQL stores attachment metadata and the object key, not the file binary.

The metadata should identify:
- Campus and related purchase
- Object key
- Original filename
- Content type
- File size
- Uploading user
- Upload timestamp
- Optional checksum

The application must:
- Validate allowed file types and maximum file size.
- Generate non-guessable object keys.
- Keep the bucket private.
- Authorize access using the user's role and campus.
- Provide short-lived signed download links where appropriate.
- Avoid exposing permanent public object URLs.

The object-storage provider and retention configuration must be selected before production deployment.

## Consequences

- Database backups remain smaller.
- Files can be stored independently of transactional records.
- Production requires object-storage credentials, access policies and backup/retention configuration.
- Local development may use a compatible local storage adapter.

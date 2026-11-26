"""Private file storage for supplier bill attachments (ADR-008).

The database keeps each attachment's metadata and object key; the file is
kept here. Storage is reached only through the API, which checks the user's
permission and campus first: files are never exposed by a public URL.

Backends:
- "local": files on disk under settings.ATTACHMENT_STORAGE_DIR, outside the
  repository. For development.
- The production S3-compatible backend is not implemented: its provider
  (decision D9) and client library are not approved yet.
"""

import os
import re
import secrets
from pathlib import Path
from typing import Protocol

from app.core.config import settings

# campus-<id>/bill-<id>/<32 hex chars>.<ext>
OBJECT_KEY = re.compile(r"^campus-\d+/bill-\d+/[0-9a-f]{32}\.(pdf|jpg|png|webp)$")


class StorageNotConfigured(RuntimeError):
    """The configured backend is not available."""


class AttachmentStorage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


def new_object_key(campus_id: int, purchase_id: int, extension: str) -> str:
    """A non-guessable key (128 random bits), as ADR-008 requires."""
    return f"campus-{campus_id}/bill-{purchase_id}/{secrets.token_hex(16)}.{extension}"


class LocalAttachmentStorage:
    def __init__(self, root: str | os.PathLike) -> None:
        self.root = Path(root).expanduser().resolve()

    def _path(self, key: str) -> Path:
        if not OBJECT_KEY.fullmatch(key):
            raise ValueError("Invalid attachment key.")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid attachment key.")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        # O_EXCL: never overwrite; the key is new for every upload.
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists():
                raise FileExistsError(key)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        """Only used to undo a save whose database row was not committed."""
        self._path(key).unlink(missing_ok=True)


def get_attachment_storage() -> AttachmentStorage:
    """FastAPI dependency: the configured storage backend."""
    if settings.ATTACHMENT_STORAGE_BACKEND == "local":
        return LocalAttachmentStorage(settings.ATTACHMENT_STORAGE_DIR)
    raise StorageNotConfigured(
        f"Attachment storage backend {settings.ATTACHMENT_STORAGE_BACKEND!r} "
        "is not available."
    )

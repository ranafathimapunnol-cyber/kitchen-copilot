"""Campus logo and photo (Phase 2 follow-up).

An upload is accepted only if its first bytes are PNG, JPEG or WebP and
Pillow can decode it within the size limits. It is then re-encoded: rotated
upright, resized, every metadata block (EXIF with GPS, comments) dropped,
and saved as a new file (logo: PNG keeping transparency, at most 512 px;
photo: JPEG, at most 1600 px). The original bytes are never stored, so no
script, polyglot or hidden metadata survives. Files live in the private
attachment storage under a random key and are served only through the API.
"""

import io
import secrets
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000          # refuse decompression bombs early
MIN_SIDE = 32


@dataclass(frozen=True)
class Kind:
    name: str
    longest_side: int
    extension: str
    content_type: str


KINDS = {
    "logo": Kind("logo", 512, "png", "image/png"),
    "photo": Kind("photo", 1600, "jpg", "image/jpeg"),
}


class MediaRejected(ValueError):
    """The upload is not an acceptable image; the message is safe to show."""


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def process(kind: Kind, data: bytes) -> bytes:
    if not data:
        raise MediaRejected("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise MediaRejected("The image is larger than 5 MB.")
    if sniff(data) is None:
        raise MediaRejected("Upload a PNG, JPEG or WebP image.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            if width * height > MAX_SOURCE_PIXELS:
                raise MediaRejected("The image has too many pixels (at most 40 megapixels).")
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            image = ImageOps.exif_transpose(image)
            if min(image.size) < MIN_SIDE:
                raise MediaRejected(f"The image is too small (at least {MIN_SIDE} px on each side).")
            image.thumbnail((kind.longest_side, kind.longest_side), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            if kind.name == "logo":
                clean = image.convert("RGBA")
                clean.save(out, format="PNG", optimize=True)
            else:
                clean = image.convert("RGB")
                clean.save(out, format="JPEG", quality=85, optimize=True, progressive=True)
            return out.getvalue()
    except MediaRejected:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise MediaRejected("The image could not be read.") from None


def new_key(campus_id: int, kind: Kind) -> str:
    return f"campus-{campus_id}/branding/{kind.name}-{secrets.token_hex(16)}.{kind.extension}"


# ---------- schema readiness (migration e2b7c4d9a5f1) ----------

MEDIA_NOT_MIGRATED = ("Campus logos and photos need migration e2b7c4d9a5f1, which is awaiting "
                      "authorization.")
_ready = False


def media_ready(db) -> bool:
    """True once the campus media columns exist. Before the migration the
    rest of the application works and campuses simply have no logo/photo."""
    global _ready
    if not _ready:
        from sqlalchemy import inspect

        _ready = any(c["name"] == "logo_key" for c in inspect(db.get_bind()).get_columns("campuses"))
    return _ready


def media_info(db, campus_id: int) -> dict:
    """{"logo": version|None, "photo": version|None}; the version changes
    whenever the file does, for cache-busting image URLs."""
    if not media_ready(db):
        return {"logo": None, "photo": None, "available": False}
    from app.models.campus import Campus

    logo, photo = db.query(Campus.logo_key, Campus.photo_key).filter(Campus.id == campus_id).one()
    version = lambda key: key.rsplit("-", 1)[-1].split(".")[0][:12] if key else None  # noqa: E731
    return {"logo": version(logo), "photo": version(photo), "available": True}

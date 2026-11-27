"""Campus logo and photo: platform-only upload, re-encoding, campus-scoped
viewing, replacement, removal, audit, and behaviour before migration M2."""

import io

import pytest
from PIL import Image

from app.core.config import settings
from app.models import Campus
from app.models.platform import PlatformAuditLog
from app.services import campus_media

from tests.test_operational_authority import act_as, client, db, world  # noqa: F401
from tests.test_platform import P, platform_as, root  # noqa: F401


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))
    return tmp_path


def image_bytes(fmt="PNG", size=(800, 600), mode="RGBA", exif_gps=False):
    image = Image.new(mode, size, (200, 240, 140, 255) if mode == "RGBA" else (200, 240, 140))
    out = io.BytesIO()
    kwargs = {}
    if exif_gps:
        exif = Image.Exif()
        exif[0x8825] = {1: "N", 2: (12.0, 58.0, 0.0)}   # GPS IFD
        exif[0x010F] = "SecretCamera"
        kwargs["exif"] = exif
    image.save(out, format=fmt, **kwargs)
    return out.getvalue()


def upload(client, campus_id, kind, data, name="x.png"):
    return client.put(f"{P}/campuses/{campus_id}/media/{kind}", files={"file": (name, data, "application/octet-stream")})


def files(path):
    return sorted(p.name for p in path.rglob("*") if p.is_file())


def test_upload_reencodes_and_campus_users_see_only_their_own(client, db, world, root, storage_dir):
    a, b = world.a, world.b
    platform_as(client, root)
    info = client.put(f"{P}/campuses/{a.campus.id}/media/logo", files={"file": ("logo.png", image_bytes(size=(2000, 1000)), "image/png")})
    assert info.status_code == 200, info.text
    assert info.json()["logo"] and info.json()["photo"] is None
    photo = upload(client, a.campus.id, "photo", image_bytes("JPEG", (3000, 2000), "RGB", exif_gps=True), "p.jpg")
    assert photo.status_code == 200, photo.text

    logo = Image.open(io.BytesIO(client.get(f"{P}/campuses/{a.campus.id}/media/logo").content))
    assert logo.format == "PNG" and max(logo.size) == 512 and logo.mode == "RGBA"
    stored = client.get(f"{P}/campuses/{a.campus.id}/media/photo")
    assert stored.headers["content-type"] == "image/jpeg" and stored.headers["x-content-type-options"] == "nosniff"
    pic = Image.open(io.BytesIO(stored.content))
    assert max(pic.size) == 1600 and not pic.getexif()                     # metadata stripped
    assert b"SecretCamera" not in stored.content
    detail = client.get(f"{P}/campuses/{a.campus.id}").json()
    assert detail["media"]["logo"] and detail["media"]["photo"]

    act_as(client, a.staff)                                                # any campus user, own campus
    assert client.get("/api/campus-media").json()["logo"] == info.json()["logo"]
    assert client.get("/api/campus-media/logo").status_code == 200
    act_as(client, b.manager)                                              # campus B sees none of A's
    assert client.get("/api/campus-media").json() == {"logo": None, "photo": None, "available": True}
    assert client.get("/api/campus-media/logo").status_code == 404


@pytest.mark.parametrize("who", ["admin", "manager", "staff"])
def test_campus_users_cannot_upload_or_read_through_the_platform(client, world, root, who):
    act_as(client, getattr(world.a, who))
    assert upload(client, world.a.campus.id, "logo", image_bytes()).status_code == 401
    assert client.delete(f"{P}/campuses/{world.a.campus.id}/media/logo").status_code == 401
    assert client.get(f"{P}/campuses/{world.b.campus.id}/media/logo").status_code == 401


@pytest.mark.parametrize("data, message", [
    (b"", "empty"),
    (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "PNG, JPEG or WebP"),
    (b"GIF89a" + b"\x00" * 100, "PNG, JPEG or WebP"),
    (b"\x89PNG\r\n\x1a\n" + b"not really a png", "could not be read"),
    (b"\xff\xd8\xff" + b"\x00" * (5 * 1024 * 1024), "larger than 5 MB"),
])
def test_bad_files_are_refused_and_audited(client, db, world, root, storage_dir, data, message):
    platform_as(client, root)
    response = upload(client, world.a.campus.id, "logo", data)
    assert response.status_code == 422 and message in response.json()["detail"]
    assert files(storage_dir) == []
    row = db.query(PlatformAuditLog).filter(PlatformAuditLog.action == "UPLOAD_MEDIA").one()
    assert row.outcome == "FAILURE"


def test_tiny_images_are_refused(client, world, root):
    platform_as(client, root)
    response = upload(client, world.a.campus.id, "logo", image_bytes(size=(10, 10)))
    assert response.status_code == 422 and "too small" in response.json()["detail"]


def test_replace_and_remove_clean_up_old_files_and_are_audited(client, db, world, root, storage_dir):
    platform_as(client, root)
    campus = world.a.campus.id
    first = upload(client, campus, "logo", image_bytes()).json()["logo"]
    second = upload(client, campus, "logo", image_bytes(size=(300, 300))).json()["logo"]
    assert first != second and len(files(storage_dir)) == 1              # old file removed
    assert client.delete(f"{P}/campuses/{campus}/media/logo").json()["logo"] is None
    assert files(storage_dir) == []
    assert client.delete(f"{P}/campuses/{campus}/media/logo").status_code == 404
    actions = [(r.action, r.outcome, r.details.get("replaced")) for r in db.query(PlatformAuditLog).order_by(PlatformAuditLog.id)
               if r.target_type == "CAMPUS"]
    assert actions == [("UPLOAD_MEDIA", "SUCCESS", False), ("UPLOAD_MEDIA", "SUCCESS", True), ("REMOVE_MEDIA", "SUCCESS", None)]
    db.expire_all()
    assert db.get(Campus, campus).logo_key is None


def test_unknown_kind_and_other_organisation(client, world, root):
    platform_as(client, root)
    assert upload(client, world.a.campus.id, "banner", image_bytes()).status_code == 404
    assert upload(client, 99999, "logo", image_bytes()).status_code == 404


def test_before_the_migration_uploads_wait_and_campus_side_shows_nothing(client, world, root, monkeypatch):
    monkeypatch.setattr(campus_media, "_ready", False)
    monkeypatch.setattr(campus_media, "media_ready", lambda db: False)
    platform_as(client, root)
    response = upload(client, world.a.campus.id, "logo", image_bytes())
    assert response.status_code == 503 and "e2b7c4d9a5f1" in response.json()["detail"]
    assert client.get(f"{P}/campuses/{world.a.campus.id}").json()["media"]["available"] is False
    act_as(client, world.a.staff)
    assert client.get("/api/campus-media").json()["available"] is False
    assert client.get("/api/campus-media/logo").status_code == 404

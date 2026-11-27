"""Campus logo and photo for the campus's own users (read-only).

Any signed-in campus user sees their own campus's images; the campus comes
from the session, never from the request. Uploads are platform-only
(app/api/routes/platform.py).
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.campus import Campus
from app.models.user import User
from app.services import campus_media
from app.services.attachment_storage import AttachmentStorage, get_attachment_storage

router = APIRouter(prefix="/api/campus-media", tags=["Campus media"])


def serve(db: Session, storage: AttachmentStorage, campus_id: int, kind: str) -> Response:
    if kind not in campus_media.KINDS or not campus_media.media_ready(db):
        raise HTTPException(status_code=404, detail="No image")
    column = Campus.logo_key if kind == "logo" else Campus.photo_key
    key = db.query(column).filter(Campus.id == campus_id).scalar()
    if not key:
        raise HTTPException(status_code=404, detail="No image")
    try:
        data = storage.read(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="No image") from None
    return Response(content=data, media_type=campus_media.KINDS[kind].content_type,
                    headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "default-src 'none'"})


@router.get("")
def own_media(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return campus_media.media_info(db, user.campus_id)


@router.get("/{kind}")
def own_media_file(kind: str, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                   storage: AttachmentStorage = Depends(get_attachment_storage)):
    return serve(db, storage, user.campus_id, kind)

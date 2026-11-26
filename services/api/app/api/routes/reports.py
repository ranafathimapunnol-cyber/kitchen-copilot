"""Operational reports (Stage 9; PROPOSAL.md §5.8, AT03): catalogue, report
and Excel / PDF export. Each report checks its own permission; an export
is a POST (CSRF) and writes an audit row. See app/services/tabular_reports.py."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.routes.master_data import record_audit
from app.db.session import get_db
from app.models.user import User
from app.services import tabular_reports as tr
from app.services.report_exports import EXPORT_MEDIA_TYPES

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class ExportInput(BaseModel):
    format: Literal["xlsx", "pdf"]
    date_from: date | None = None
    date_to: date | None = None
    supplier_id: int | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, gt=0)
    item_id: int | None = Field(default=None, gt=0)
    meal_session_id: int | None = Field(default=None, gt=0)
    compare: Literal["elapsed", "full", "previous"] = "elapsed"


@router.get("/catalog")
def report_catalog(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The reports this user may open (each report's own permission)."""
    return {"items": tr.catalogue(db, user)}


@router.get("/lookups")
def report_lookups(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Filter choices for the reports this user may open: categories, items
    and meal sessions; suppliers only with bill or inventory access."""
    from sqlalchemy import func

    from app.api.dependencies import user_has_permission
    from app.models.master_data import Category, Item, MealSession, Supplier

    if not tr.catalogue(db, user):
        return {"categories": [], "items": [], "suppliers": [], "meal_sessions": []}
    campus_id = user.campus_id
    suppliers = []
    if user_has_permission(db, user, "purchase_bill.read") or user_has_permission(db, user, "inventory.read"):
        suppliers = [{"id": s.id, "name": s.name} for s in db.query(Supplier).filter(
            Supplier.campus_id == campus_id).order_by(func.lower(Supplier.name))]
    return {
        "categories": [{"id": c.id, "name": c.name} for c in db.query(Category).filter(
            Category.campus_id == campus_id).order_by(func.lower(Category.name))],
        "items": [{"id": i.id, "name": i.name, "category_id": i.category_id} for i in db.query(Item).filter(
            Item.campus_id == campus_id).order_by(func.lower(Item.name))],
        "suppliers": suppliers,
        "meal_sessions": [{"id": m.id, "name": m.name} for m in db.query(MealSession).filter(
            MealSession.campus_id == campus_id).order_by(MealSession.id)],
    }


@router.get("/{key}")
def run_report(
    key: str,
    date_from: date | None = Query(default=None), date_to: date | None = Query(default=None),
    supplier_id: int | None = Query(default=None, gt=0), category_id: int | None = Query(default=None, gt=0),
    item_id: int | None = Query(default=None, gt=0), meal_session_id: int | None = Query(default=None, gt=0),
    compare: Literal["elapsed", "full", "previous"] = Query(default="elapsed"),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    return tr.build(db, user, key, tr.Params(date_from, date_to, supplier_id, category_id, item_id, meal_session_id, compare))


@router.post("/{key}/export")
def export_report(key: str, payload: ExportInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.tabular_exports import export_filename, render_pdf, render_xlsx

    report = tr.build(db, user, key, tr.Params(payload.date_from, payload.date_to, payload.supplier_id, payload.category_id,
                                               payload.item_id, payload.meal_session_id, payload.compare))
    content = render_xlsx(report, user.full_name) if payload.format == "xlsx" else render_pdf(report, user.full_name)
    filename = export_filename(report, payload.format)
    record_audit(db, user, "EXPORT", "REPORT", None, {"report": key, "format": payload.format, "file_name": filename,
                                                       "period": report["period"], "filters": report["filters"],
                                                       "rows": report["row_count"], "bytes": len(content)})
    db.commit()
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[payload.format], headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})

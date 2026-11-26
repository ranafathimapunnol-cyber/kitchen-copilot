"""Purchases versus supplier payments for a reporting period (PUR04).

Purchase expenditure and supplier payments are reported separately, as
the proposal requires (section 5.8 and PUR04 criterion 5):
- purchase expenditure: supplier bills dated in the period (bill date);
- supplier payments: payments dated in the period (payment date), broken
  down by payment method, with cash shown on its own.

Each supplier row also carries its net payable before and after the
period, so the report reconciles:

    closing = opening + billed - paid

Net payable is bills minus payments up to that date, never floored, so an
overpayment shows as a negative balance (a credit) rather than as zero.

Every report states its period and filters; amounts are in INR, returned
as two-place decimal strings. Supplier-return credits are not included
until client question Q6 is answered.

Exports: the same report as Excel or PDF (POST .../export), built by the
same function with the same filters; every export is written to the audit
log. A print-friendly view is provided by the web page.

Access: purchase_bill.read (ADMIN and KITCHEN_MANAGER; STAFF only through
an existing explicit assignment), limited to the user's campus. Exports use
the same permission; there is no separate EXPORT permission.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.api.routes.master_data import record_audit
from app.api.routes.supplier_payments import (
    PAYMENT_METHODS,
    ZERO,
    money,
    money_text,
)
from app.db.session import get_db
from app.models import Campus
from app.models.master_data import Supplier
from app.models.purchases import Purchase, SupplierPayment
from app.models.user import User
from app.services.report_exports import (
    EXPORT_MEDIA_TYPES,
    export_filename,
    render_pdf,
    render_xlsx,
)

router = APIRouter(prefix="/api/reports", tags=["Reports"])


# ============================================================
# GROUPED TOTALS (one query each, grouped by supplier)
# ============================================================

def bill_totals(
    db: Session, campus_id: int, supplier_id: int | None, *conditions
) -> dict[int, tuple[int, Decimal]]:
    query = db.query(
        Purchase.supplier_id,
        func.count(Purchase.id),
        func.coalesce(func.sum(Purchase.grand_total), 0),
    ).filter(Purchase.campus_id == campus_id, *conditions)

    if supplier_id is not None:
        query = query.filter(Purchase.supplier_id == supplier_id)

    return {
        sid: (int(count), money(total))
        for sid, count, total in query.group_by(Purchase.supplier_id).all()
    }


def payment_totals(
    db: Session, campus_id: int, supplier_id: int | None, *conditions
) -> dict[int, tuple[int, Decimal, Decimal]]:
    """Per supplier: payment count, amount paid, and the cash part."""

    query = (
        db.query(
            Purchase.supplier_id,
            func.count(SupplierPayment.id),
            func.coalesce(func.sum(SupplierPayment.amount), 0),
            func.coalesce(
                func.sum(
                    case(
                        (SupplierPayment.payment_method == "CASH",
                         SupplierPayment.amount),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .join(
            Purchase,
            (Purchase.id == SupplierPayment.purchase_id)
            & (Purchase.campus_id == campus_id),
        )
        .filter(SupplierPayment.campus_id == campus_id, *conditions)
    )

    if supplier_id is not None:
        query = query.filter(Purchase.supplier_id == supplier_id)

    return {
        sid: (int(count), money(paid), money(cash))
        for sid, count, paid, cash in query.group_by(Purchase.supplier_id).all()
    }


def method_totals(
    db: Session, campus_id: int, supplier_id: int | None, *conditions
) -> dict[str, tuple[int, Decimal]]:
    query = (
        db.query(
            SupplierPayment.payment_method,
            func.count(SupplierPayment.id),
            func.coalesce(func.sum(SupplierPayment.amount), 0),
        )
        .join(
            Purchase,
            (Purchase.id == SupplierPayment.purchase_id)
            & (Purchase.campus_id == campus_id),
        )
        .filter(SupplierPayment.campus_id == campus_id, *conditions)
    )

    if supplier_id is not None:
        query = query.filter(Purchase.supplier_id == supplier_id)

    found = {
        method: (int(count), money(total))
        for method, count, total in query.group_by(
            SupplierPayment.payment_method
        ).all()
    }

    # Every approved method is listed, even at zero. A method outside the
    # list (data written before the list existed) is kept, so the
    # breakdown always adds up to the total paid.
    return {
        **{method: found.get(method, (0, ZERO)) for method in PAYMENT_METHODS},
        **{m: v for m, v in found.items() if m not in PAYMENT_METHODS},
    }


# ============================================================
# REPORT
# ============================================================

def build_purchases_vs_payments(
    db: Session,
    user: User,
    date_from: date,
    date_to: date,
    supplier_id: int | None,
) -> dict:
    """The report itself. The screen and every export (Excel, PDF) call
    this one function with the same period and supplier, so their figures
    and filters are always the same."""

    if date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from cannot be after date_to.",
        )

    campus_id = user.campus_id
    supplier_name = None

    if supplier_id is not None:
        supplier_name = (
            db.query(Supplier.name)
            .filter(Supplier.id == supplier_id, Supplier.campus_id == campus_id)
            .scalar()
        )
        if supplier_name is None:
            raise HTTPException(status_code=404, detail="Supplier not found")

    in_period_bill = (
        Purchase.purchase_date >= date_from,
        Purchase.purchase_date <= date_to,
    )
    in_period_payment = (
        SupplierPayment.payment_date >= date_from,
        SupplierPayment.payment_date <= date_to,
    )

    billed = bill_totals(db, campus_id, supplier_id, *in_period_bill)
    paid = payment_totals(db, campus_id, supplier_id, *in_period_payment)
    billed_before = bill_totals(
        db, campus_id, supplier_id, Purchase.purchase_date < date_from
    )
    paid_before = payment_totals(
        db, campus_id, supplier_id, SupplierPayment.payment_date < date_from
    )
    methods = method_totals(db, campus_id, supplier_id, *in_period_payment)

    rows = []
    for sid in set(billed) | set(paid) | set(billed_before) | set(paid_before):
        bill_count, billed_amount = billed.get(sid, (0, ZERO))
        payment_count, paid_amount, cash_amount = paid.get(sid, (0, ZERO, ZERO))
        opening = (
            billed_before.get(sid, (0, ZERO))[1]
            - paid_before.get(sid, (0, ZERO, ZERO))[1]
        )
        closing = opening + billed_amount - paid_amount

        # A supplier with no activity in the period and nothing owed either
        # way is left out.
        if not (bill_count or payment_count or opening or closing):
            continue

        rows.append({
            "supplier_id": sid,
            "bill_count": bill_count,
            "billed": billed_amount,
            "payment_count": payment_count,
            "paid": paid_amount,
            "paid_cash": cash_amount,
            "opening_balance": opening,
            "closing_balance": closing,
        })

    names = dict(
        db.query(Supplier.id, Supplier.name)
        .filter(
            Supplier.campus_id == campus_id,
            Supplier.id.in_([row["supplier_id"] for row in rows] or [0]),
        )
        .all()
    )
    rows.sort(key=lambda row: ((names.get(row["supplier_id"]) or "").lower(),
                               row["supplier_id"]))

    def total(key):
        return sum((row[key] for row in rows), ZERO)

    money_keys = ("billed", "paid", "paid_cash", "opening_balance",
                  "closing_balance")

    return {
        "period": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
        "filters": {
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
        },
        "campus": {
            "id": campus_id,
            "name": db.query(Campus.name).filter(Campus.id == campus_id).scalar(),
        },
        "currency": "INR",
        "basis": {
            "purchases": "Supplier bills dated in the period (bill date).",
            "payments": "Supplier payments dated in the period (payment date).",
            "balances": "Net payable: bills minus payments up to the date; "
                        "negative means overpaid.",
            "excluded": "Supplier-return credits (client question Q6).",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suppliers": [
            {
                **row,
                "supplier_name": names.get(row["supplier_id"]),
                **{key: money_text(row[key]) for key in money_keys},
            }
            for row in rows
        ],
        "totals": {
            "supplier_count": len(rows),
            "bill_count": sum(row["bill_count"] for row in rows),
            "payment_count": sum(row["payment_count"] for row in rows),
            **{key: money_text(total(key)) for key in money_keys},
            "paid_by_method": [
                {"payment_method": method, "payment_count": count,
                 "amount": money_text(amount)}
                for method, (count, amount) in methods.items()
            ],
        },
    }


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/purchases-vs-payments")
def purchases_vs_payments(
    date_from: date = Query(...),
    date_to: date = Query(...),
    supplier_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.read")),
):
    return build_purchases_vs_payments(db, user, date_from, date_to, supplier_id)


class ReportExportRequest(BaseModel):
    format: Literal["xlsx", "pdf"]
    date_from: date
    date_to: date
    supplier_id: int | None = Field(default=None, gt=0)


@router.post("/purchases-vs-payments/export")
def export_purchases_vs_payments(
    payload: ReportExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.read")),
):
    """The same report as an Excel or PDF file.

    It is built by build_purchases_vs_payments with the requested period
    and supplier, exactly like the screen, and only laid out by the
    renderer. It is a POST so the CSRF check applies: an export writes an
    audit row, which another site must not be able to trigger. Access uses
    the report's read permission; there is no separate EXPORT permission.
    """
    report = build_purchases_vs_payments(
        db, user, payload.date_from, payload.date_to, payload.supplier_id
    )

    # Rendered before the audit row is written, so a failed rendering never
    # records an export that did not happen.
    if payload.format == "xlsx":
        content = render_xlsx(report, user.full_name)
    else:
        content = render_pdf(report, user.full_name)

    filename = export_filename(report, payload.format)
    totals = report["totals"]

    record_audit(
        db,
        user,
        "EXPORT",
        "PURCHASE_REPORT",
        None,
        {
            "report": "purchases_vs_payments",
            "format": payload.format,
            "file_name": filename,
            "date_from": report["period"]["date_from"],
            "date_to": report["period"]["date_to"],
            "supplier_id": report["filters"]["supplier_id"],
            "supplier_name": report["filters"]["supplier_name"],
            "supplier_rows": len(report["suppliers"]),
            "billed": totals["billed"],
            "paid": totals["paid"],
            "closing_balance": totals["closing_balance"],
            "bytes": len(content),
        },
    )
    db.commit()

    return Response(
        content=content,
        media_type=EXPORT_MEDIA_TYPES[payload.format],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )

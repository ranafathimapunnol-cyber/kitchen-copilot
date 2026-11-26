"""Supplier payments and balances (PUR04).

A payment always belongs to one supplier bill (a `purchases` row).
Balances are derived from bill totals and recorded payments; nothing is
stored.

Access (confirmed role rules, 17 November 2026):
- ADMIN and KITCHEN_MANAGER record and view payments and balances.
- STAFF only through an existing, active, explicit assignment:
  purchase_bill.create to record, purchase_bill.read to view.
  Assignments are honoured exactly as stored; nothing here changes them.
- There is no approval step. A recorded payment counts immediately.

Rules:
- Payments may be recorded against DRAFT bills; there is no posting step.
- The payment date cannot be later than today (in the campus time zone,
  settings.APP_TIMEZONE) or earlier than the bill date.
- A payment cannot exceed the bill's outstanding balance. A bill with
  nothing outstanding (fully paid, or a zero total) takes no payment.
- A bill whose payments exceed its total (possible only through data
  written outside this API) is reported as OVERPAID with the excess,
  never hidden as a zero balance.
- Supplier-return credits are not part of balances until client question
  Q6 is answered.
- payment_method is one of PAYMENT_METHODS.
- A reference number can be used only once per bill.
- Money is returned as decimal strings with two places ("1250.50").
- Every payment writes an audit row in the same transaction.
- Payments cannot be edited, voided or deleted. Correcting one needs a
  schema change that has not been approved.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.api.routes.master_data import record_audit
from app.core.clock import campus_today
from app.db.session import get_db
from app.models.master_data import Supplier
from app.models.purchases import Purchase, SupplierPayment
from app.models.user import User

router = APIRouter(tags=["Supplier Payments"])

MONEY = Decimal("0.01")
ZERO = Decimal("0.00")

PAYMENT_METHODS = ("CASH", "BANK_TRANSFER", "UPI", "CHEQUE", "OTHER")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def today() -> date:
    """Today in the campus time zone (not the server's UTC clock).
    A function so tests can pin it."""
    return campus_today()


# ============================================================
# REQUEST SCHEMA
# ============================================================

class PaymentCreate(BaseModel):
    payment_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    payment_method: Literal[PAYMENT_METHODS]  # type: ignore[valid-type]
    reference_number: str | None = Field(default=None, max_length=100)
    remarks: str | None = Field(default=None, max_length=500)

    @field_validator("payment_method", mode="before")
    @classmethod
    def normalise_method(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("reference_number", "remarks")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


# ============================================================
# MONEY AND BALANCE HELPERS
# ============================================================

def money(value) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(
        MONEY, rounding=ROUND_HALF_UP
    )


def money_text(value) -> str:
    return format(money(value), "f")


def page_meta(total: int, page: int, page_size: int) -> dict:
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def paid_total(db: Session, campus_id: int, purchase_id: int) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(SupplierPayment.amount), 0))
        .filter(
            SupplierPayment.campus_id == campus_id,
            SupplierPayment.purchase_id == purchase_id,
        )
        .scalar()
    )
    return money(total)


def payment_status(grand_total: Decimal, paid: Decimal) -> str:
    if paid > grand_total:
        return "OVERPAID"
    if paid == grand_total:
        # Includes a zero-total bill: nothing is owed, so it is settled.
        return "PAID"
    if paid <= 0:
        return "UNPAID"
    return "PARTIALLY_PAID"


def bill_balance(
    purchase: Purchase, paid, supplier_name: str | None = None
) -> dict:
    grand_total = money(purchase.grand_total)
    paid = money(paid)
    difference = grand_total - paid

    return {
        "purchase_id": purchase.id,
        "supplier_id": purchase.supplier_id,
        "supplier_name": supplier_name,
        "invoice_number": purchase.invoice_number,
        "purchase_date": purchase.purchase_date.isoformat(),
        "grand_total": money_text(grand_total),
        "paid_total": money_text(paid),
        "outstanding": money_text(max(difference, ZERO)),
        "overpaid": money_text(max(-difference, ZERO)),
        "payment_status": payment_status(grand_total, paid),
    }


def serialize_payment(
    payment: SupplierPayment, recorded_by_name: str | None = None
) -> dict:
    return {
        "id": payment.id,
        "purchase_id": payment.purchase_id,
        "payment_date": payment.payment_date.isoformat(),
        "amount": money_text(payment.amount),
        "payment_method": payment.payment_method,
        "reference_number": payment.reference_number,
        "remarks": payment.remarks,
        "created_by": payment.created_by,
        "created_by_name": recorded_by_name,
        "created_at": payment.created_at.isoformat(),
    }


def supplier_name_for(db: Session, purchase: Purchase) -> str | None:
    return (
        db.query(Supplier.name)
        .filter(
            Supplier.id == purchase.supplier_id,
            Supplier.campus_id == purchase.campus_id,
        )
        .scalar()
    )


def get_campus_bill(
    db: Session, user: User, purchase_id: int, lock: bool = False
) -> Purchase:
    query = db.query(Purchase).filter(
        Purchase.id == purchase_id,
        Purchase.campus_id == user.campus_id,
    )
    if lock:
        # Serialises concurrent payments on the same bill, so two requests
        # cannot both pass the overpayment check.
        query = query.with_for_update()

    purchase = query.first()

    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")

    return purchase


def bill_paid_subquery(db: Session, campus_id: int):
    """Total paid per bill in one campus, for joining onto purchases."""
    return (
        db.query(
            SupplierPayment.purchase_id.label("purchase_id"),
            func.sum(SupplierPayment.amount).label("paid"),
        )
        .filter(SupplierPayment.campus_id == campus_id)
        .group_by(SupplierPayment.purchase_id)
        .subquery()
    )


def supplier_balance_subquery(
    db: Session, campus_id: int, supplier_id: int | None = None
):
    """One row per supplier with bills: billed, paid, outstanding and
    overpaid. Outstanding and overpaid are summed bill by bill, so an
    overpaid bill never hides another bill's unpaid amount."""

    paid_sq = bill_paid_subquery(db, campus_id)
    paid = func.coalesce(paid_sq.c.paid, 0)
    balance = Purchase.grand_total - paid

    query = (
        db.query(
            Purchase.supplier_id.label("supplier_id"),
            func.count(Purchase.id).label("bill_count"),
            func.sum(case((balance > 0, 1), else_=0)).label("open_bill_count"),
            func.sum(Purchase.grand_total).label("billed"),
            func.sum(paid).label("paid"),
            func.sum(case((balance > 0, balance), else_=0)).label(
                "outstanding"
            ),
            func.sum(case((balance < 0, -balance), else_=0)).label(
                "overpaid"
            ),
        )
        .outerjoin(paid_sq, paid_sq.c.purchase_id == Purchase.id)
        .filter(Purchase.campus_id == campus_id)
    )

    if supplier_id is not None:
        query = query.filter(Purchase.supplier_id == supplier_id)

    return query.group_by(Purchase.supplier_id).subquery()


def balance_totals(db: Session, balances) -> dict:
    row = db.query(
        func.coalesce(func.sum(balances.c.billed), 0),
        func.coalesce(func.sum(balances.c.paid), 0),
        func.coalesce(func.sum(balances.c.outstanding), 0),
        func.coalesce(func.sum(balances.c.overpaid), 0),
        func.coalesce(func.sum(balances.c.open_bill_count), 0),
        func.count(),
    ).one()

    return {
        "total_billed": money_text(row[0]),
        "total_paid": money_text(row[1]),
        "outstanding": money_text(row[2]),
        "overpaid": money_text(row[3]),
        "open_bill_count": int(row[4] or 0),
        "supplier_count": int(row[5] or 0),
    }


def serialize_supplier_balance(row, supplier_name: str | None) -> dict:
    return {
        "supplier_id": row.supplier_id,
        "supplier_name": supplier_name,
        "bill_count": int(row.bill_count),
        "open_bill_count": int(row.open_bill_count or 0),
        "total_billed": money_text(row.billed),
        "total_paid": money_text(row.paid),
        "outstanding": money_text(row.outstanding),
        "overpaid": money_text(row.overpaid),
    }


# ============================================================
# RECORD A PAYMENT
# Permission: purchase_bill.create
# ============================================================

@router.post(
    "/api/purchases/{purchase_id}/payments",
    status_code=status.HTTP_201_CREATED,
)
def record_supplier_payment(
    purchase_id: int,
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.create")),
):
    purchase = get_campus_bill(db, user, purchase_id, lock=True)

    if payload.payment_date > today():
        raise HTTPException(
            status_code=422,
            detail="Payment date cannot be in the future.",
        )

    if payload.payment_date < purchase.purchase_date:
        raise HTTPException(
            status_code=422,
            detail=(
                "Payment date cannot be earlier than the bill date "
                f"({purchase.purchase_date.isoformat()})."
            ),
        )

    grand_total = money(purchase.grand_total)
    paid = paid_total(db, user.campus_id, purchase.id)
    outstanding = grand_total - paid
    amount = money(payload.amount)

    if outstanding <= 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "This bill has a zero total, so there is nothing to pay."
                if grand_total == 0
                else "This bill is already fully paid."
            ),
        )

    if amount > outstanding:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Payment of {money_text(amount)} exceeds the outstanding "
                f"balance of {money_text(outstanding)}."
            ),
        )

    if payload.reference_number:
        duplicate = (
            db.query(SupplierPayment.id)
            .filter(
                SupplierPayment.campus_id == user.campus_id,
                SupplierPayment.purchase_id == purchase.id,
                func.lower(SupplierPayment.reference_number)
                == payload.reference_number.lower(),
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This reference number is already recorded for this bill."
                ),
            )

    paid_after = money(paid + amount)
    status_after = payment_status(grand_total, paid_after)

    payment = SupplierPayment(
        campus_id=user.campus_id,
        purchase_id=purchase.id,
        payment_date=payload.payment_date,
        amount=amount,
        payment_method=payload.payment_method,
        reference_number=payload.reference_number,
        remarks=payload.remarks,
        created_by=user.id,
    )

    try:
        db.add(payment)
        db.flush()

        record_audit(
            db,
            user,
            "CREATE",
            "SUPPLIER_PAYMENT",
            payment.id,
            {
                "purchase_id": purchase.id,
                "invoice_number": purchase.invoice_number,
                "supplier_id": purchase.supplier_id,
                "payment_date": payload.payment_date.isoformat(),
                "amount": money_text(amount),
                "payment_method": payment.payment_method,
                "reference_number": payment.reference_number,
                "bill_total": money_text(grand_total),
                "paid_before": money_text(paid),
                "paid_after": money_text(paid_after),
                "outstanding_after": money_text(outstanding - amount),
                "payment_status_after": status_after,
            },
        )

        db.commit()
        db.refresh(payment)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Payment could not be saved because of an invalid record.",
        )

    return {
        "payment": serialize_payment(payment, user.full_name),
        "bill": bill_balance(
            purchase, paid_after, supplier_name_for(db, purchase)
        ),
    }


# ============================================================
# PAYMENTS AND BALANCE FOR ONE BILL
# Permission: purchase_bill.read
# ============================================================

@router.get("/api/purchases/{purchase_id}/payments")
def list_bill_payments(
    purchase_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.read")),
):
    purchase = get_campus_bill(db, user, purchase_id)

    rows = (
        db.query(SupplierPayment, User.full_name)
        .outerjoin(User, User.id == SupplierPayment.created_by)
        .filter(
            SupplierPayment.campus_id == user.campus_id,
            SupplierPayment.purchase_id == purchase.id,
        )
        .order_by(SupplierPayment.payment_date, SupplierPayment.id)
        .all()
    )

    paid = money(sum((money(p.amount) for p, _name in rows), ZERO))

    return {
        "bill": bill_balance(purchase, paid, supplier_name_for(db, purchase)),
        "payments": [serialize_payment(p, name) for p, name in rows],
    }


# ============================================================
# ALL PAYMENTS IN THE CAMPUS (paginated)
# Permission: purchase_bill.read
# ============================================================

@router.get("/api/supplier-payments")
def list_supplier_payments(
    supplier_id: int | None = Query(default=None, gt=0),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    payment_method: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.read")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from cannot be after date_to.",
        )

    method = payment_method.strip().upper() if payment_method else None
    if method and method not in PAYMENT_METHODS:
        raise HTTPException(
            status_code=422,
            detail=f"payment_method must be one of {', '.join(PAYMENT_METHODS)}.",
        )

    query = (
        db.query(SupplierPayment)
        .join(
            Purchase,
            (Purchase.id == SupplierPayment.purchase_id)
            & (Purchase.campus_id == user.campus_id),
        )
        .filter(SupplierPayment.campus_id == user.campus_id)
    )

    if supplier_id is not None:
        query = query.filter(Purchase.supplier_id == supplier_id)
    if date_from is not None:
        query = query.filter(SupplierPayment.payment_date >= date_from)
    if date_to is not None:
        query = query.filter(SupplierPayment.payment_date <= date_to)
    if method:
        query = query.filter(SupplierPayment.payment_method == method)

    total = query.count()
    total_paid = query.with_entities(
        func.coalesce(func.sum(SupplierPayment.amount), 0)
    ).scalar()

    rows = (
        query.with_entities(
            SupplierPayment,
            Purchase.invoice_number,
            Purchase.supplier_id,
            Supplier.name,
            User.full_name,
        )
        .outerjoin(
            Supplier,
            (Supplier.id == Purchase.supplier_id)
            & (Supplier.campus_id == user.campus_id),
        )
        .outerjoin(User, User.id == SupplierPayment.created_by)
        .order_by(
            SupplierPayment.payment_date.desc(),
            SupplierPayment.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                **serialize_payment(payment, recorded_by),
                "invoice_number": invoice_number,
                "supplier_id": bill_supplier_id,
                "supplier_name": supplier_name,
            }
            for (
                payment,
                invoice_number,
                bill_supplier_id,
                supplier_name,
                recorded_by,
            ) in rows
        ],
        **page_meta(total, page, page_size),
        "total_paid": money_text(total_paid),
    }


# ============================================================
# BILLS WITH THEIR BALANCES (paginated)
# Permission: purchase_bill.read
# ============================================================

@router.get("/api/supplier-balances/bills")
def list_bill_balances(
    supplier_id: int | None = Query(default=None, gt=0),
    open_only: bool = Query(default=False),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.read")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from cannot be after date_to.",
        )

    paid_sq = bill_paid_subquery(db, user.campus_id)
    paid = func.coalesce(paid_sq.c.paid, 0)

    query = (
        db.query(Purchase)
        .outerjoin(paid_sq, paid_sq.c.purchase_id == Purchase.id)
        .filter(Purchase.campus_id == user.campus_id)
    )

    if supplier_id is not None:
        query = query.filter(Purchase.supplier_id == supplier_id)
    if open_only:
        query = query.filter(Purchase.grand_total - paid > 0)
    if date_from is not None:
        query = query.filter(Purchase.purchase_date >= date_from)
    if date_to is not None:
        query = query.filter(Purchase.purchase_date <= date_to)

    term = search.strip() if search else ""
    if term:
        # Invoice number contains the term, ignoring case. LIKE wildcards
        # typed by the user are matched literally.
        escaped = (
            term.lower()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        query = query.filter(
            func.lower(Purchase.invoice_number).like(
                f"%{escaped}%", escape="\\"
            )
        )

    total = query.count()

    rows = (
        query.with_entities(Purchase, paid.label("paid"), Supplier.name)
        .outerjoin(
            Supplier,
            (Supplier.id == Purchase.supplier_id)
            & (Supplier.campus_id == user.campus_id),
        )
        .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            bill_balance(purchase, bill_paid, supplier_name)
            for purchase, bill_paid, supplier_name in rows
        ],
        **page_meta(total, page, page_size),
    }


# ============================================================
# SUPPLIER BALANCES (paginated)
# Permission: purchase_bill.read
# ============================================================

@router.get("/api/supplier-balances")
def supplier_balances(
    supplier_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_bill.read")),
):
    balances = supplier_balance_subquery(db, user.campus_id, supplier_id)
    totals = balance_totals(db, balances)

    rows = (
        db.query(balances, Supplier.name)
        .outerjoin(
            Supplier,
            (Supplier.id == balances.c.supplier_id)
            & (Supplier.campus_id == user.campus_id),
        )
        .order_by(
            balances.c.outstanding.desc(),
            Supplier.name,
            balances.c.supplier_id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            serialize_supplier_balance(row, row.name) for row in rows
        ],
        **page_meta(totals["supplier_count"], page, page_size),
        "totals": totals,
    }

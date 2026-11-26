"""Human approval and execution of agent proposals (Stage 12, ADR-010).

Interim in-process form of the Actions boundary (ADR-005 names a separate
Flask Actions service; see docs). The contract is the same:
1. load the proposal within the approver's campus and lock it;
2. it must be PENDING and not expired (idempotent: a second approval is
   refused, so there is never a duplicate business effect);
3. re-check the approver's role and permission now, not when proposed;
4. execute only through the existing application function for that action
   (which validates, writes its own audit row and commits);
5. record the decision and result on the proposal plus an audit row.

The approver is always a person; the agent never approves.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import user_has_permission
from app.api.routes.master_data import record_audit
from app.core.config import settings
from app.models.agent import AgentProposal
from app.models.user import User, UserRole

PLANNERS = (UserRole.ADMIN, UserRole.KITCHEN_MANAGER)
ACTION_ROLES = {
    "CREATE_MEAL_PLAN_DRAFT": PLANNERS,
    "CREATE_PURCHASE_ORDER_DRAFT": (UserRole.ADMIN, UserRole.KITCHEN_MANAGER, UserRole.STAFF),
    "RAISE_STOCK_ADJUSTMENT_REQUEST": PLANNERS,
}


def expired(p: AgentProposal) -> bool:
    created = p.created_at if p.created_at.tzinfo else p.created_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created > timedelta(hours=settings.AGENT_PROPOSAL_TTL_HOURS)


def can_decide(db: Session, user: User, p: AgentProposal) -> bool:
    return user.role in ACTION_ROLES.get(p.action_type, ()) and user_has_permission(db, user, p.required_permission)


def load(db: Session, user: User, proposal_id: int) -> AgentProposal:
    p = (db.query(AgentProposal).filter(AgentProposal.id == proposal_id, AgentProposal.campus_id == user.campus_id)
         .with_for_update().first())
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if p.status == "PENDING" and expired(p):
        p.status = "EXPIRED"
        db.commit()
    if p.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"This proposal is already {p.status.lower()}.")
    if not can_decide(db, user, p):
        raise HTTPException(status_code=403, detail="You are not authorised to decide this proposal.")
    return p


def execute(db: Session, user: User, p: AgentProposal) -> dict:
    data = p.payload
    if p.action_type == "CREATE_MEAL_PLAN_DRAFT":
        from app.api.routes.planning import LineInput, PlanCreate, create_plan
        payload = PlanCreate(plan_date=data["plan_date"], meal_session_id=data["meal_session_id"], menu_id=data["menu_id"],
                             expected_headcount=data["expected_headcount"], notes=data.get("notes"),
                             lines=[LineInput(item_id=l["item_id"]) for l in data["lines"]])
        plan = create_plan(payload=payload, db=db, user=user)
        return {"entity": "MEAL_PLAN", "id": plan["id"], "number": plan["plan_number"], "href": "/dashboard/meal-plans"}
    if p.action_type == "CREATE_PURCHASE_ORDER_DRAFT":
        from app.api.routes.purchase_orders import OrderInput, OrderLineInput, create_order
        payload = OrderInput(supplier_id=data["supplier_id"], order_date=data["order_date"],
                             expected_date=data.get("expected_date"), remarks=data.get("remarks"),
                             items=[OrderLineInput(item_id=i["item_id"], quantity=Decimal(i["quantity"]),
                                                   unit_id=i["unit_id"]) for i in data["items"]])
        order = create_order(payload=payload, db=db, user=user)
        return {"entity": "PURCHASE_ORDER", "id": order["id"], "number": order["order_number"],
                "href": "/dashboard/purchase-orders"}
    if p.action_type == "RAISE_STOCK_ADJUSTMENT_REQUEST":
        from app.api.routes.kitchen import Reason
        from app.api.routes.stock_counts import raise_adjustment
        result = raise_adjustment(count_id=data["count_id"], line_id=data["line_id"],
                                  payload=Reason(reason=data["reason"]), db=db, user=user)
        return {"entity": "STOCK_ADJUSTMENT", "id": result.get("id"), "number": data.get("count_number"),
                "href": "/dashboard/stock-counts"}
    raise HTTPException(status_code=422, detail="Unknown action")


def approve(db: Session, user: User, proposal_id: int, note: str | None) -> AgentProposal:
    p = load(db, user, proposal_id)
    now = datetime.now(timezone.utc)
    p.status, p.decided_by, p.decided_at, p.decision_note = "EXECUTING", user.id, now, note
    record_audit(db, user, "APPROVE", "AGENT_PROPOSAL", p.id, {"action": p.action_type, "title": p.title,
                                                               "note": note})
    db.flush()
    proposal_id = p.id
    try:
        # The application function validates, writes its audit row and commits
        # (the approval above commits with it).
        result = execute(db, user, p)
    except HTTPException as exc:
        db.rollback()
        p = db.query(AgentProposal).filter(AgentProposal.id == proposal_id).with_for_update().one()
        p.status, p.decided_by, p.decided_at, p.decision_note = "FAILED", user.id, now, note
        p.error = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        record_audit(db, user, "EXECUTION_FAILED", "AGENT_PROPOSAL", p.id, {"action": p.action_type, "error": p.error})
        db.commit()
        return p
    p = db.query(AgentProposal).filter(AgentProposal.id == proposal_id).with_for_update().one()
    p.status, p.result = "EXECUTED", result
    record_audit(db, user, "EXECUTED", "AGENT_PROPOSAL", p.id, {"action": p.action_type, "result": result})
    db.commit()
    return p


def reject(db: Session, user: User, proposal_id: int, reason: str) -> AgentProposal:
    p = load(db, user, proposal_id)
    p.status, p.decided_by, p.decided_at, p.decision_note = "REJECTED", user.id, datetime.now(timezone.utc), reason
    record_audit(db, user, "REJECT", "AGENT_PROPOSAL", p.id, {"action": p.action_type, "reason": reason})
    db.commit()
    return p

"""Kitchen Copilot API (Stage 12).

Off unless AGENT_ENABLED is true (the status endpoint always answers, so
the screen can say the assistant is turned off). Campus users only; each
user sees their own conversations. Proposals are visible to everyone in
the campus who may decide them, and to their author.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agent import engine, executor, knowledge
from app.agent import tools as T
from app.agent.intent import llm_available
from app.api.dependencies import get_current_user
from app.api.routes.master_data import record_audit
from app.core.clock import utc_iso
from app.core.config import settings
from app.db.session import get_db
from app.models.agent import AgentConversation, AgentMessage, AgentProposal, AgentStep
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/agent", tags=["Kitchen Copilot"])
MESSAGES_PER_10_MIN = 30
WORKFLOW_TOOLS = {"plan_procure": "meal_options", "explain_spending": "spending_comparison",
                  "stock_difference": "latest_count_line", "attention": "operations_overview"}


def campus_user(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if user.role == UserRole.SUPER_ADMIN or user.campus_id is None:
        raise HTTPException(status_code=403, detail="Kitchen Copilot is for campus users.")
    # Owner request 27 Nov 2026: STAFF use Copilot only when an Admin has
    # assigned copilot.read; ADMIN and KITCHEN_MANAGER always may.
    from app.api.dependencies import user_has_permission

    if not user_has_permission(db, user, "copilot.read"):
        raise HTTPException(status_code=403, detail="Kitchen Copilot has not been assigned to you.")
    return user


def enabled_user(user: User = Depends(campus_user)) -> User:
    if not settings.AGENT_ENABLED:
        raise HTTPException(status_code=503, detail="Kitchen Copilot is turned off (AGENT_ENABLED=false).")
    return user


class MessageInput(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    conversation_id: int | None = Field(default=None, gt=0)
    # The screen the person is viewing; focuses answers, grants nothing.
    page: str | None = Field(default=None, max_length=120, pattern=r"^/dashboard(/[a-z0-9-]+){0,4}$")


class Decision(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class Rejection(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def names(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.query(User.id, User.full_name).filter(User.id.in_(ids or {0})))


def proposal_out(db: Session, user: User, p: AgentProposal, people: dict | None = None) -> dict:
    people = people or names(db, [p.created_by, p.decided_by])
    status = "EXPIRED" if p.status == "PENDING" and executor.expired(p) else p.status
    return {"id": p.id, "conversation_id": p.conversation_id, "workflow": p.workflow, "action_type": p.action_type,
            "title": p.title, "rationale": p.rationale, "payload": p.payload, "status": status,
            "required_permission": p.required_permission, "created_at": utc_iso(p.created_at),
            "created_by_name": people.get(p.created_by), "decided_by_name": people.get(p.decided_by),
            "decided_at": utc_iso(p.decided_at) if p.decided_at else None, "decision_note": p.decision_note,
            "result": p.result or {}, "error": p.error,
            "can_decide": status == "PENDING" and executor.can_decide(db, user, p)}


def message_out(m: AgentMessage) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "payload": m.payload or {}, "created_at": utc_iso(m.created_at)}


def own_conversation(db: Session, user: User, conversation_id: int) -> AgentConversation:
    c = db.query(AgentConversation).filter(AgentConversation.id == conversation_id,
                                           AgentConversation.campus_id == user.campus_id,
                                           AgentConversation.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return c


@router.get("/status")
def agent_status(db: Session = Depends(get_db), user: User = Depends(campus_user)):
    return {
        "enabled": settings.AGENT_ENABLED,
        "reader": "gemini" if llm_available() else "rules",
        "external_model": settings.GEMINI_MODEL if llm_available() else None,
        "procedures_loaded": len(knowledge.documents()),
        "workflows": {w: T.allowed(db, user, tool) for w, tool in WORKFLOW_TOOLS.items()},
        "proposal_ttl_hours": settings.AGENT_PROPOSAL_TTL_HOURS,
    }


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(enabled_user)):
    rows = (db.query(AgentConversation).filter(AgentConversation.campus_id == user.campus_id,
                                               AgentConversation.user_id == user.id)
            .order_by(AgentConversation.updated_at.desc()).limit(50).all())
    return {"items": [{"id": c.id, "title": c.title, "updated_at": utc_iso(c.updated_at)} for c in rows]}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(enabled_user)):
    c = own_conversation(db, user, conversation_id)
    messages = db.query(AgentMessage).filter(AgentMessage.conversation_id == c.id).order_by(AgentMessage.id).all()
    proposals = db.query(AgentProposal).filter(AgentProposal.conversation_id == c.id).order_by(AgentProposal.id).all()
    people = names(db, [p.created_by for p in proposals] + [p.decided_by for p in proposals])
    return {"id": c.id, "title": c.title, "messages": [message_out(m) for m in messages],
            "proposals": [proposal_out(db, user, p, people) for p in proposals]}


@router.get("/conversations/{conversation_id}/trace")
def conversation_trace(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(enabled_user)):
    c = own_conversation(db, user, conversation_id)
    steps = db.query(AgentStep).filter(AgentStep.conversation_id == c.id).order_by(AgentStep.id).all()
    return {"items": [{"id": s.id, "message_id": s.message_id, "seq": s.seq, "kind": s.kind, "name": s.name,
                       "input": s.input, "output": s.output, "ok": s.ok, "duration_ms": s.duration_ms,
                       "created_at": utc_iso(s.created_at)} for s in steps]}


@router.post("/messages")
def send_message(payload: MessageInput, db: Session = Depends(get_db), user: User = Depends(enabled_user)):
    text = " ".join(payload.text.split())
    since = datetime.now(timezone.utc) - timedelta(minutes=10)
    recent = (db.query(func.count(AgentMessage.id)).join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
              .filter(AgentConversation.user_id == user.id, AgentMessage.role == "user", AgentMessage.created_at >= since)
              .scalar())
    if recent >= MESSAGES_PER_10_MIN:
        raise HTTPException(status_code=429, detail="Too many messages. Wait a few minutes and try again.")
    if payload.conversation_id:
        conversation = own_conversation(db, user, payload.conversation_id)
    else:
        conversation = AgentConversation(campus_id=user.campus_id, user_id=user.id, title=text[:120])
        db.add(conversation)
        db.flush()
    last = (db.query(AgentMessage).filter(AgentMessage.conversation_id == conversation.id, AgentMessage.role == "assistant")
            .order_by(AgentMessage.id.desc()).first())
    earlier = (last.payload or {}).get("intent") if last and (last.payload or {}).get("status") == "needs_info" else None
    question = AgentMessage(conversation_id=conversation.id, campus_id=user.campus_id, role="user", content=text, payload={})
    db.add(question)
    db.flush()
    reply, trace = engine.run_turn(db, user, conversation.id, text, earlier, payload.page)
    # The tool calls of this turn, for the "checked …" status line.
    tools = [{"name": s.name, "ok": s.ok, "ms": s.duration_ms} for s in trace.steps if s.kind == "tool"]
    answer = AgentMessage(conversation_id=conversation.id, campus_id=user.campus_id, role="assistant",
                          content="\n\n".join(reply.text), payload={**reply.payload(), "tools": tools})
    db.add(answer)
    db.flush()
    for step in trace.steps:
        step.message_id = answer.id
    for p in reply.proposals:
        p.message_id = answer.id
    conversation.updated_at = datetime.now(timezone.utc)
    record_audit(db, user, "ASK", "AGENT_CONVERSATION", conversation.id, {
        "message_id": answer.id, "workflow": reply.intent.workflow, "page": payload.page, "status": reply.status,
        "reader": reply.intent.reader, "tools": [s.name for s in trace.steps if s.kind == "tool"],
        "proposals": [p.id for p in reply.proposals]})
    db.commit()
    people = names(db, [user.id])
    return {"conversation_id": conversation.id, "title": conversation.title, "question": message_out(question),
            "answer": message_out(answer), "proposals": [proposal_out(db, user, p, people) for p in reply.proposals]}


@router.get("/proposals")
def list_proposals(status: str | None = Query(default=None, pattern="^(PENDING|EXECUTED|FAILED|REJECTED|EXPIRED)$"),
                   db: Session = Depends(get_db), user: User = Depends(enabled_user)):
    rows = (db.query(AgentProposal).filter(AgentProposal.campus_id == user.campus_id)
            .order_by(AgentProposal.id.desc()).limit(200).all())
    visible = [p for p in rows if p.created_by == user.id or executor.can_decide(db, user, p)]
    people = names(db, [p.created_by for p in visible] + [p.decided_by for p in visible])
    items = [proposal_out(db, user, p, people) for p in visible]
    if status:
        items = [i for i in items if i["status"] == status]
    return {"items": items}


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: int, payload: Decision | None = None, db: Session = Depends(get_db),
                     user: User = Depends(enabled_user)):
    p = executor.approve(db, user, proposal_id, (payload.note.strip() or None) if payload and payload.note else None)
    return proposal_out(db, user, p)


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, payload: Rejection, db: Session = Depends(get_db),
                    user: User = Depends(enabled_user)):
    p = executor.reject(db, user, proposal_id, payload.reason.strip())
    return proposal_out(db, user, p)

"""Kitchen Copilot agent engine (Stage 12, PROPOSAL.md §7.2).

One turn: understand the request -> make a plan (shown to the user) ->
run permission-checked tools -> explain the findings with the
application's own figures -> store any consequential action as a PENDING
proposal for human approval (app/agent/executor.py). Nothing here writes
business data.

Workflows: plan_procure, explain_spending, stock_difference, and the
read-only attention summary (what needs attention, optionally focused on
the screen the person is viewing).
"""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.agent import tools as T
from app.agent.intent import Intent, understand
from app.core.clock import campus_today
from app.models.agent import AgentMessage, AgentProposal
from app.models.master_data import Item, MealSession, Menu
from app.models.user import User

WORKFLOW_TITLES = {
    "plan_procure": "Plan and procure",
    "explain_spending": "Explain spending",
    "stock_difference": "Investigate a stock difference",
    "attention": "What needs attention",
}
HELP = ("I can help with these jobs:\n"
        "• What needs attention — e.g. \"What needs my attention today?\" (on any screen, I focus on that screen)\n"
        "• Plan and procure — e.g. \"Plan tomorrow's lunch for 450 people and tell me what we need to buy.\"\n"
        "• Explain spending — e.g. \"Why did food spending go up this month compared with last month?\"\n"
        "• Investigate a stock difference — e.g. \"Today's rice count is 12 kg below the system. Find out why.\"")


class Reply:
    def __init__(self, intent: Intent):
        self.intent = intent
        self.text: list[str] = []
        self.plan: list[str] = []
        self.blocks: list[dict] = []
        self.choices: list[dict] = []
        self.links: list[dict] = []
        self.sources: list[dict] = []
        self.proposals: list[AgentProposal] = []
        self.status = "answered"

    def say(self, line: str):
        self.text.append(line)

    page: str | None = None

    def payload(self) -> dict:
        return {"status": self.status, "workflow": self.intent.workflow, "intent": self.intent.as_dict(),
                "page": self.page,
                "plan": self.plan, "blocks": self.blocks, "choices": self.choices, "links": self.links,
                "sources": self.sources, "proposal_ids": [p.id for p in self.proposals],
                "reader": self.intent.reader, "notes": self.intent.notes}


def money(value) -> str:
    amount = Decimal(str(value))
    sign = "−" if amount < 0 else ""
    return f"{sign}₹{abs(amount):,.2f}"


def pct(value) -> str:
    return "not comparable" if value is None else f"{Decimal(str(value)):+.1f}%"


def day_text(value: str | date) -> str:
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}"


# How an item compares between the two periods (purchase_analytics statuses).
STATUS_TEXT = {"NEW": "not bought before", "NOT_BOUGHT_NOW": "not bought this period",
               "INCOMPATIBLE": "units not comparable"}


def ask(reply: Reply, question: str, choices: list[tuple[str, str]]):
    reply.status = "needs_info"
    reply.say(question)
    reply.choices = [{"label": label, "text": text} for label, text in choices[:12]]


def deny(reply: Reply, what: str):
    reply.status = "not_allowed"
    reply.say(f"You don't have access to {what}, so I can't do this for you. "
              "Ask your Admin if you need this permission.")


def add_procedures(trace: T.Trace, reply: Reply, topic: str):
    found = T.call(trace, "procedures", topic=topic)
    if found["matches"]:
        reply.sources = [{"source": m["source"], "title": m["title"], "excerpt": m["excerpt"]} for m in found["matches"]]
    else:
        reply.sources = []
        reply.say("Procedure guidance: unavailable from the approved sources (no approved procedure document "
                  "covers this yet).")


def same_pending(trace: T.Trace, action: str, payload: dict) -> AgentProposal | None:
    """An identical proposal on this campus still waiting for a decision."""
    from app.agent.executor import expired

    wanted = json.dumps(jsonable_encoder(payload), sort_keys=True)
    for p in trace.db.query(AgentProposal).filter(AgentProposal.campus_id == trace.user.campus_id,
                                                  AgentProposal.action_type == action,
                                                  AgentProposal.status == "PENDING"):
        if not expired(p) and json.dumps(jsonable_encoder(p.payload), sort_keys=True) == wanted:
            return p
    return None


def propose(trace: T.Trace, reply: Reply, workflow: str, action: str, title: str, rationale: str, payload: dict,
            permission: str) -> AgentProposal | None:
    # Asking again must not queue the same action twice: in this conversation
    # the waiting proposal is shown again; from another one it is named.
    existing = same_pending(trace, action, payload)
    if existing:
        trace.record("plan", "propose", {"action": action, "title": title},
                     {"existing_proposal_id": existing.id, "created": False})
        if existing.conversation_id == trace.conversation_id:
            reply.proposals.append(existing)
        else:
            reply.say(f"The same proposal (\u201c{existing.title}\u201d) is already waiting for a decision under "
                      "Proposals to review, so I have not prepared it again.")
        return existing
    p = AgentProposal(campus_id=trace.user.campus_id, conversation_id=trace.conversation_id, workflow=workflow,
                      action_type=action, title=title[:300], rationale=rationale, payload=payload,
                      required_permission=permission, status="PENDING", created_by=trace.user.id, result={})
    trace.db.add(p)
    trace.db.flush()
    trace.record("plan", "propose", {"action": action, "title": title}, {"proposal_id": p.id})
    reply.proposals.append(p)
    return p


# ============================================================
# 1. PLAN AND PROCURE
# ============================================================

def plan_procure(trace: T.Trace, reply: Reply, today: date):
    db, user, intent = trace.db, trace.user, reply.intent
    reply.plan = ["Find the date, meal session, menu and headcount", "Read the approved per-person standards in effect",
                  "Calculate required quantities with the application's planning formula",
                  "Compare with current stock and work out what to buy",
                  "Prepare a draft meal plan and draft purchase orders for your approval"]
    if not T.allowed(db, user, "meal_options"):
        return deny(reply, "meal planning")
    options = T.call(trace, "meal_options")
    if not intent.plan_date:
        return ask(reply, "Which date should I plan for?",
                   [("Today", "today"), ("Tomorrow", "tomorrow"), ("Day after tomorrow", "day after tomorrow")])
    if date.fromisoformat(intent.plan_date) < today:
        intent.plan_date = None
        return ask(reply, "Meal plans are made for today or a later date. Which date should I plan for?",
                   [("Today", "today"), ("Tomorrow", "tomorrow")])
    sessions = options["meal_sessions"]
    if not intent.meal_session_id:
        return ask(reply, "Which meal session?", [(s["name"], s["name"]) for s in sessions])
    menus = [m for m in options["menus"] if m["meal_session_id"] == intent.meal_session_id]
    if not menus:
        with_menus = {m["meal_session_id"] for m in options["menus"]}
        others = [(s["name"], s["name"]) for s in sessions if s["id"] != intent.meal_session_id and s["id"] in with_menus]
        if not others:
            return ask(reply, "No meal session has an active menu yet, so there is nothing to plan. "
                              "An Admin or Kitchen Manager can add menus on the Menus screen.", [])
        intent.meal_session_id = None
        return ask(reply, "That meal session has no active menu. Choose another session.", others)
    if not intent.menu_id or intent.menu_id not in {m["id"] for m in menus}:
        if len(menus) == 1:
            intent.menu_id = menus[0]["id"]
        else:
            return ask(reply, "Which menu?", [(m["name"], m["name"]) for m in menus])
    session_name = next(s["name"] for s in sessions if s["id"] == intent.meal_session_id)
    menu_name = next(m["name"] for m in menus if m["id"] == intent.menu_id)
    need = T.call(trace, "plan_requirements", plan_date=date.fromisoformat(intent.plan_date),
                  meal_session_id=intent.meal_session_id, menu_id=intent.menu_id, headcount=intent.headcount)
    if not need["headcount"]:
        return ask(reply, f"How many people should I plan {session_name} on {day_text(intent.plan_date)} for? "
                          "There is no meal record with an expected headcount yet.",
                   [("400 people", "400 people"), ("450 people", "450 people"), ("500 people", "500 people")])
    intent.headcount = need["headcount"]
    if not need["lines"]:
        reply.say(f"{menu_name} has no approved per-person standard in effect on {day_text(intent.plan_date)}, "
                  "so I can't calculate quantities. Approve standards on the Portion Standards screen first.")
        reply.links.append({"label": "Portion standards", "href": "/dashboard/portion-standards"})
        return
    reply.say(f"{session_name} on {day_text(intent.plan_date)}, menu {menu_name}, for {need['headcount']} people "
              f"(headcount from {need['headcount_source']}).")
    rows = [[l["item_name"], l["standard"], f'{l["required"]} {l["base_unit_symbol"]}' if l["required"] else "—",
             f'{l["available_stock"]} {l["base_unit_symbol"]}',
             f'{l["gap"]} {l["base_unit_symbol"]}' if l["gap"] not in (None, "0", "0.000") and Decimal(l["gap"]) > 0
             else "Nothing"] for l in need["lines"]]
    reply.blocks.append({"type": "table", "title": "Requirements (application calculation)",
                         "columns": ["Item", "Approved standard", "Required", "In stock now", "To buy"], "rows": rows,
                         "note": need["availability_note"]})
    for w in need["warnings"]:
        reply.say(f"Note: {w}")
    if need["unavailable_items"]:
        reply.blocks.append({"type": "list", "title": "Not included",
                             "items": [f'{u["item_name"]}: {u["reason"]}' for u in need["unavailable_items"]]})
    add_procedures(trace, reply, f"{menu_name} {session_name} meal planning quantities preparation")

    if need["existing_plan"]:
        ep = need["existing_plan"]
        reply.say(f"A meal plan already exists for this slot ({ep['plan_number']}, {ep['status'].lower()}), "
                  "so I won't propose another.")
        reply.links.append({"label": ep["plan_number"], "href": "/dashboard/meal-plans"})
    else:
        lines = [{"item_id": l["item_id"]} for l in need["lines"]]
        propose(trace, reply, "plan_procure", "CREATE_MEAL_PLAN_DRAFT",
                f"Draft meal plan: {session_name}, {day_text(intent.plan_date)} ({need['headcount']} people)",
                f"Uses the approved standards of {menu_name}; required quantities as shown. The plan is saved as a "
                "DRAFT; approving it stays on the Meal Plans screen.",
                {"plan_date": intent.plan_date, "meal_session_id": intent.meal_session_id, "menu_id": intent.menu_id,
                 "expected_headcount": need["headcount"], "lines": lines,
                 "notes": "Prepared by Kitchen Copilot and approved by a person."},
                "meal_plan.create")

    gaps = [l for l in need["lines"] if l["gap"] and Decimal(l["gap"]) > 0]
    if not gaps:
        reply.say("Current stock covers every item; nothing needs to be bought.")
        return
    if not T.allowed(db, user, "last_suppliers"):
        reply.say(f"{len(gaps)} item(s) need buying. You don't have purchase-order access, so I haven't prepared orders.")
        return
    suppliers = T.call(trace, "last_suppliers", item_ids=[l["item_id"] for l in gaps])["by_item"]
    groups: dict[int, dict] = {}
    unsourced = []
    for l in gaps:
        s = suppliers.get(l["item_id"])
        if not s:
            unsourced.append(l["item_name"])
            continue
        g = groups.setdefault(s["supplier_id"], {"name": s["supplier_name"], "items": []})
        g["items"].append(l)
    order_date = today
    expected = date.fromisoformat(intent.plan_date) if date.fromisoformat(intent.plan_date) >= today else None
    for supplier_id, g in groups.items():
        items = [{"item_id": l["item_id"], "quantity": l["gap"], "unit_id": l["base_unit_id"],
                  "item_name": l["item_name"], "unit_symbol": l["base_unit_symbol"]} for l in g["items"]]
        propose(trace, reply, "plan_procure", "CREATE_PURCHASE_ORDER_DRAFT",
                f"Draft purchase order to {g['name']} ({len(items)} item{'s' if len(items) != 1 else ''})",
                f"Shortfall against current stock for {session_name} on {day_text(intent.plan_date)}; supplier is the "
                "one each item was last bought from. Saved as a DRAFT; placing the order stays on the Purchase "
                "Orders screen.",
                {"supplier_id": supplier_id, "supplier_name": g["name"], "order_date": order_date.isoformat(),
                 "expected_date": expected.isoformat() if expected else None,
                 "remarks": f"For {session_name} on {intent.plan_date} (Kitchen Copilot proposal).", "items": items},
                "purchase_order.create")
    if unsourced:
        reply.say("No earlier supplier on record for: " + ", ".join(unsourced) +
                  ". Add these to a purchase order yourself.")


# ============================================================
# 2. EXPLAIN SPENDING (read-only)
# ============================================================

def explain_spending(trace: T.Trace, reply: Reply, today: date):
    db, user, intent = trace.db, trace.user, reply.intent
    reply.plan = ["Work out the period and the comparison period (and whether the period is still running)",
                  "Read purchase quantities, prices and totals with the spending-analysis tool",
                  "Separate price effects from quantity effects (application formula)",
                  "Add headcount from meal records", "Explain the main drivers with links to the source bills"]
    if not T.allowed(db, user, "spending_comparison"):
        return deny(reply, "supplier bills and spending figures")
    if not intent.date_from:
        intent.date_from, intent.date_to = today.replace(day=1).isoformat(), today.isoformat()
        intent.notes.append("No period was given, so I used this month to date.")
    start, end = date.fromisoformat(intent.date_from), date.fromisoformat(intent.date_to)
    if end > today:
        end = today
        intent.date_to = end.isoformat()
    # An item named in the request narrows to that item; otherwise a category.
    scope = {"item_id": intent.item_id} if intent.item_id else {"category_id": intent.category_id} if intent.category_id else {}
    data = T.call(trace, "spending_comparison", date_from=start, date_to=end, compare=intent.compare, **scope)
    cur, prev = data["periods"]["current"], data["periods"]["previous"]
    t = data["totals"]
    running = end == today and (end + timedelta(days=1)).month == end.month
    scope_name = (data.get("filters") or {}).get("item_name") or (data.get("filters") or {}).get("category_name")
    if scope_name:
        reply.say(f"This covers {scope_name} only, from the bill lines (bill-level discounts and charges belong to no "
                  "item or category, so they are not included).")
    reply.say(f"{scope_name + ' spending' if scope_name else 'Spending'} from {day_text(cur['date_from'])} to {day_text(cur['date_to'])} was {money(t['current'])}, "
              f"against {money(t['previous'])} for {day_text(prev['date_from'])} to {day_text(prev['date_to'])}: "
              f"a change of {money(t['change'])} ({pct(t['change_percent'])}).")
    if running:
        reply.say("This period is still running, so it is compared with the same number of days earlier "
                  "rather than a whole month." if intent.compare == "elapsed" else "This period is still running.")
    if Decimal(t["line_change"]) != 0:
        reply.say(f"On the item lines, price changes account for {money(t['price_effect'])} and quantity changes for "
                  f"{money(t['quantity_effect'])}; {money(t['unexplained_by_items'])} comes from items bought in only "
                  "one period or without a comparable unit.")
    drivers = [r for r in data["items"] if Decimal(r["value_change"]) != 0][:6]
    if drivers:
        reply.blocks.append({"type": "table", "title": "Main drivers (largest changes)",
                             "columns": ["Item", "Spend change", "Avg price change", "Quantity change",
                                         "Price effect", "Quantity effect"],
                             "rows": [[r["item_name"], money(r["value_change"]), pct(r["price_change_percent"]),
                                       f'{r["quantity_change"]} {r["standard_unit_symbol"] or ""}'.strip()
                                       if r["status"] == "COMPARABLE" else STATUS_TEXT.get(r["status"], r["status"].lower()),
                                       money(r["price_effect"]) if r["price_effect"] else "—",
                                       money(r["quantity_effect"]) if r["quantity_effect"] else "—"] for r in drivers]})
        top = drivers[0]
        cause = ("price" if top["price_effect"] and top["quantity_effect"] and
                 abs(Decimal(top["price_effect"])) >= abs(Decimal(top["quantity_effect"])) else "quantity")
        if top["status"] == "COMPARABLE":
            reply.say(f"The biggest single driver is {top['item_name']} ({money(top['value_change'])}), mostly from "
                      f"{'a higher average price' if cause == 'price' and Decimal(top['price_effect']) > 0 else 'a lower average price' if cause == 'price' else 'buying more' if Decimal(top['quantity_effect']) > 0 else 'buying less'}.")
    cats = [c for c in data["categories"] if Decimal(c["value_change"]) != 0][:5]
    if cats:
        reply.blocks.append({"type": "table", "title": "By category", "columns": ["Category", "Current", "Previous", "Change"],
                             "rows": [[c["category_name"] or "—", money(c["current_value"]), money(c["previous_value"]),
                                       f'{money(c["value_change"])} ({pct(c["value_change_percent"])})'] for c in cats]})
    if T.allowed(db, user, "headcount_summary"):
        heads = T.call(trace, "headcount_summary", periods={"current": cur, "previous": prev})
        c, p = heads["current"]["average_daily_headcount"], heads["previous"]["average_daily_headcount"]
        if c or p:
            reply.say(f"Average daily headcount (meal records): {c if c is not None else 'not recorded'} now, "
                      f"{p if p is not None else 'not recorded'} before.")
    if t["excluded_lines"]:
        reply.say(f"{t['excluded_lines']} bill line(s) had no explicit unit conversion and were left out of the "
                  "price comparison.")
    reply.say("Bill-level discounts and extra charges are not shared out to items (open question Q5).")
    q = f"?date_from={cur['date_from']}&date_to={cur['date_to']}&compare={intent.compare}"
    q += "".join(f"&{key}={value}" for key, value in scope.items())
    reply.links.append({"label": "Open in Spending Analysis (source bills)", "href": f"/dashboard/analytics{q}"})


# ============================================================
# 3. INVESTIGATE A STOCK DIFFERENCE
# ============================================================

def stock_difference(trace: T.Trace, reply: Reply, today: date, text: str):
    db, user, intent = trace.db, trace.user, reply.intent
    reply.plan = ["Find the physical count of the item", "Read stock movements up to the count time",
                  "Look for receipts, kitchen issues and returns recorded but not posted",
                  "Check the approved stock verification procedure",
                  "Explain the difference; propose an adjustment request only if records don't explain it"]
    if not (T.allowed(db, user, "latest_count_line") and T.allowed(db, user, "item_movements")):
        return deny(reply, "stock counts and the stock ledger")
    if not intent.item_id:
        from app.models.stock import StockCount, StockCountItem
        recent = (db.query(Item.name).join(StockCountItem, StockCountItem.item_id == Item.id)
                  .join(StockCount, StockCount.id == StockCountItem.count_id)
                  .filter(StockCount.campus_id == user.campus_id, StockCountItem.difference != 0)
                  .order_by(StockCount.counted_at.desc()).limit(30).all())
        names = list(dict.fromkeys(n for (n,) in recent))[:8]
        return ask(reply, "Which item's count should I look into?" +
                   ("" if names else " (No recent count shows a difference.)"), [(n, n) for n in names])
    item = T.call(trace, "find_item", item_id=intent.item_id)
    found = T.call(trace, "latest_count_line", item_id=intent.item_id,
                   on_or_before=date.fromisoformat(intent.plan_date) if intent.plan_date else None)
    if not found["count"]:
        reply.say(f"No physical count of {item['name']} is recorded"
                  f"{' on or before ' + day_text(intent.plan_date) if intent.plan_date else ''}. "
                  "Record the count on the Stock Counts screen first, then ask me again.")
        reply.links.append({"label": "Stock counts", "href": "/dashboard/stock-counts"})
        return
    count, line = found["count"], found["line"]
    unit = line["standard_unit_symbol"]
    diff = Decimal(line["difference"])
    counted_at = datetime.fromisoformat(count["counted_at"].replace("Z", "+00:00"))
    reply.say(f"{count['count_number']} ({day_text(counted_at.date())}, counted by {count['counted_by_name']}): "
              f"{item['name']} physical {line['physical_quantity']} {unit}, system {line['system_balance']} {unit}, "
              f"difference {diff:+} {unit}.")
    reply.links.append({"label": count["count_number"], "href": "/dashboard/stock-counts"})
    if diff == 0:
        reply.say("The count matches the system; there is nothing to investigate.")
        return
    moves = T.call(trace, "item_movements", item_id=intent.item_id, since=counted_at - timedelta(days=14),
                   until=counted_at)
    if moves["movements"]:
        reply.blocks.append({"type": "table", "title": "Movements in the 14 days before the count",
                             "columns": ["When", "Type", "Change", "Balance after", "Reference"],
                             "rows": [[m["effective_at"][:16].replace("T", " "), m["movement_type"].replace("_", " ").lower(),
                                       f'{m["signed_quantity"]} {unit}', f'{m["balance_after"]} {unit}',
                                       m.get("document_number") or m.get("invoice_number") or "—"]
                                      for m in moves["movements"][:20]]})
    else:
        reply.say("No stock movement was recorded for this item in the 14 days before the count.")
    drafts = T.call(trace, "unposted_documents", item_id=intent.item_id)
    findings = []
    if line["ledger_changed"]:
        findings.append("Stock records were posted or reversed after the count for a time before it, so the system "
                        "balance at the count time has changed since the count was recorded.")
    if drafts["draft_receipts"] and diff > 0:
        findings.append(f"{len(drafts['draft_receipts'])} goods receipt(s) with this item are still drafts: goods may "
                        "be on the shelf but not yet in the system (would explain a surplus).")
    if drafts["draft_issues"] and diff < 0:
        findings.append(f"{len(drafts['draft_issues'])} kitchen issue(s) with this item are still drafts: stock may "
                        "have gone to the kitchen without being posted (would explain a shortage).")
    if drafts["draft_returns"] and diff > 0:
        findings.append(f"{len(drafts['draft_returns'])} kitchen return(s) with this item are still drafts (would "
                        "explain a surplus).")
    if line["unit_symbol"] != unit:
        findings.append(f"The count was entered in {line['unit_symbol']} and converted with factor "
                        f"{line['conversion_factor']}; check the unit if the difference is a round multiple.")
    if line["other_pending_adjustment"]:
        findings.append(f"Another adjustment request for this item is pending "
                        f"({line['other_pending_adjustment']['count_number']}).")
    add_procedures(trace, reply, "stock verification physical count adjustment difference")
    if findings:
        reply.blocks.append({"type": "list", "title": "Possible explanations from the records", "items": findings})
    else:
        reply.say("The recorded receipts, issues, returns and corrections don't explain the difference.")
    if line["adjustment"]:
        reply.say(f"An adjustment request already exists for this count line ({line['adjustment']['status'].lower()}).")
        return
    explained = bool(drafts["draft_receipts"] or drafts["draft_issues"] or drafts["draft_returns"]
                     or line["ledger_changed"])
    if explained or not line["can_raise"]:
        reply.say("I'm not proposing an adjustment: resolve the records above first (post or cancel the drafts, "
                  "or recount), then ask again.")
        return
    propose(trace, reply, "stock_difference", "RAISE_STOCK_ADJUSTMENT_REQUEST",
            f"Adjustment request: {item['name']} {diff:+} {unit} ({count['count_number']})",
            "The records don't explain the difference. This only raises a request; posting needs approval on the "
            "Stock Counts screen by an Admin or Kitchen Manager who did not do the count.",
            {"count_id": count["id"], "line_id": line["id"], "count_number": count["count_number"],
             "item_name": item["name"], "difference": str(diff), "unit": unit,
             "reason": f"Physical count {count['count_number']} differs by {diff:+} {unit}; no unposted or "
                       "corrected records explain it (Kitchen Copilot investigation)."},
            "stock_count.create")


# ============================================================
# WHAT NEEDS ATTENTION (read only)
# ============================================================

# Screens (path prefixes) and the overview sections that matter there.
PAGE_FOCUS = (
    (("/dashboard/stock", "/dashboard/items", "/dashboard/opening-stock", "/dashboard/kitchen-issues",
      "/dashboard/waste-tracking", "/dashboard/categories", "/dashboard/units", "/dashboard/unit-conversions"),
     "stock", ("stock", "counts", "kitchen")),
    (("/dashboard/purchase-orders", "/dashboard/receipts", "/dashboard/supplier", "/dashboard/purchase-payment-report"),
     "purchasing", ("payments", "spending", "stock")),
    (("/dashboard/meals", "/dashboard/meal-plans", "/dashboard/meal-sessions", "/dashboard/menus",
      "/dashboard/menu-main-items", "/dashboard/portion-standards"),
     "meals and planning", ("headcount", "meals", "planning", "outsourced")),
    (("/dashboard/outsourced-food",), "outsourced food", ("outsourced", "meals")),
    (("/dashboard/analytics", "/dashboard/reports"), "spending and reports", ("spending", "payments", "stock")),
)
ALL_SECTIONS = ("headcount", "meals", "planning", "stock", "counts", "kitchen", "outsourced", "spending", "payments")

# Follow-up questions offered with the summary, by screen.
FOLLOW_UPS = {
    "stock": [("Investigate a count difference", "Investigate the latest stock count difference")],
    "purchasing": [("Explain spending", "Why did spending change this month?"),
                   ("Plan and procure", "Plan tomorrow's lunch and tell me what to buy")],
    "meals and planning": [("Plan tomorrow", "Plan tomorrow's lunch and tell me what to buy")],
    "spending and reports": [("Explain spending", "Why did spending change this month?")],
}


def page_focus(page: str | None) -> tuple[str | None, tuple[str, ...]]:
    for prefixes, label, keys in PAGE_FOCUS:
        if page and any(page == p or page.startswith(p + "/") or (p.endswith("supplier") and page.startswith(p))
                        for p in prefixes):
            return label, keys
    return None, ALL_SECTIONS


def qty(value) -> str:
    text = f"{Decimal(str(value)):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def findings(data: dict, keys: tuple[str, ...]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(needs attention, for information): sentences with the screen to act on."""
    act: list[tuple[str, str]] = []
    info: list[tuple[str, str]] = []
    for key in keys:
        d = data.get(key)
        if d is None:
            continue
        if key == "headcount":
            if d["today"] is None:
                act.append(("Today's headcount has not been recorded on a meal record yet.", "/dashboard/meals"))
            else:
                basis = "actual" if d.get("today_basis") == "actual" else "expected"
                info.append((f"Today's headcount: {d['today']:,} ({basis}).", "/dashboard/meals"))
        elif key == "meals":
            if d["awaiting_close_count"]:
                act.append((f"{plural(d['awaiting_close_count'], 'meal record')} from earlier days "
                            f"{'is' if d['awaiting_close_count'] == 1 else 'are'} still open.", "/dashboard/meals"))
            if d["open_count"]:
                info.append((f"{plural(d['open_count'], 'meal record')} open in total.", "/dashboard/meals"))
        elif key == "planning":
            if d["draft_plans"]:
                act.append((f"{plural(d['draft_plans'], 'meal plan')} still in draft.", "/dashboard/meal-plans"))
            if d["draft_standards"]:
                act.append((f"{plural(d['draft_standards'], 'portion standard')} still in draft.",
                            "/dashboard/portion-standards"))
            info.append((f"{plural(len(d['upcoming']), 'meal plan')} for the next 7 days.", "/dashboard/meal-plans"))
        elif key == "stock":
            if d["below_minimum"]:
                names = ", ".join(f"{r['item_name']} ({qty(r['balance'])} of {qty(r['minimum'])}{' ' + r['unit'] if r['unit'] else ''})"
                                  for r in d["lowest"][:4])
                act.append((f"{plural(d['below_minimum'], 'item')} below minimum stock: {names}"
                            f"{' and more' if d['below_minimum'] > 4 else ''}.", "/dashboard/stock"))
            if d["out_of_stock"]:
                act.append((f"{d['out_of_stock']} of {d['items_tracked']} tracked items are out of stock.",
                            "/dashboard/stock"))
            if not d["below_minimum"] and not d["out_of_stock"]:
                info.append((f"All {d['items_tracked']} tracked items are at or above minimum.", "/dashboard/stock"))
        elif key == "counts" and d["pending_adjustments"]:
            act.append((f"{plural(d['pending_adjustments'], 'stock adjustment')} waiting for approval.",
                        "/dashboard/stock-adjustments"))
        elif key == "kitchen" and d["draft_issues"]:
            act.append((f"{plural(d['draft_issues'], 'kitchen issue')} recorded but not posted.",
                        "/dashboard/kitchen-issues"))
        elif key == "outsourced":
            if d["draft_deliveries"]:
                act.append((f"{plural(d['draft_deliveries'], 'outsourced delivery', 'outsourced deliveries')} "
                            "to confirm.", "/dashboard/outsourced-food"))
            if d["waiting_for_meal_record"]:
                act.append((f"{plural(d['waiting_for_meal_record'], 'outsourced order')} waiting for a meal record.",
                            "/dashboard/meals"))
        elif key == "spending":
            change = pct(d["change_percent"])
            info.append((f"Purchases this month: {money(d['current'])} ({change} against the same days last month).",
                         "/dashboard/analytics"))
        elif key == "payments":
            if d["open_bill_count"]:
                info.append((f"Outstanding payables: {money(d['outstanding'])} on {plural(d['open_bill_count'], 'open bill')} "
                             f"to {plural(d['suppliers_owed'], 'supplier')}.", "/dashboard/supplier-balances"))
    return act, info


def attention(trace: T.Trace, reply: Reply, page: str | None):
    label, keys = page_focus(page)
    reply.plan = ["Read the campus overview through the dashboard's own permission checks",
                  f"Pick out what matters for {label}" if label else "Pick out anything that needs action",
                  "List each finding with the screen where it can be handled"]
    data = T.call(trace, "operations_overview")
    act, info = findings(data, keys)
    if label and not act and not info:
        # Nothing on this screen's topics is visible to this user; widen.
        label, (act, info) = None, findings(data, ALL_SECTIONS)
    where = f" for {label}" if label else ""
    campus = data.get("campus_name") or "your campus"
    if act:
        reply.say(f"{plural(len(act), 'thing')} at {campus} need{'s' if len(act) == 1 else ''} attention{where}.")
        reply.blocks.append({"type": "list", "title": "Needs attention", "items": [t for t, _h in act]})
    elif info:
        reply.say(f"Nothing at {campus} needs action{where} right now.")
    else:
        reply.say("You don't have access to any of the figures this summary uses. Ask your Admin if you need them.")
    if info:
        reply.blocks.append({"type": "list", "title": "For information", "items": [t for t, _h in info]})
    seen: set[str] = set()
    for _t, href in act + info:
        if href not in seen:
            seen.add(href)
            reply.links.append({"label": LINK_LABELS.get(href, "Open"), "href": href})
    reply.choices = [{"label": a, "text": b} for a, b in FOLLOW_UPS.get(label or "", [])]


LINK_LABELS = {"/dashboard/meals": "Meal records", "/dashboard/meal-plans": "Meal plans",
               "/dashboard/portion-standards": "Portion standards", "/dashboard/stock": "Stock",
               "/dashboard/stock-adjustments": "Stock adjustments", "/dashboard/kitchen-issues": "Kitchen issues",
               "/dashboard/outsourced-food": "Outsourced food", "/dashboard/analytics": "Spending analytics",
               "/dashboard/supplier-balances": "Supplier balances"}


# ============================================================
# TURN
# ============================================================

def run_turn(db: Session, user: User, conversation_id: int, text: str, earlier: dict | None,
             page: str | None = None) -> tuple[Reply, T.Trace]:
    """`page` is the screen the person is viewing (a /dashboard path). It only
    focuses the attention summary and the suggestions; access is decided by
    the user's own role and permissions, never by the page."""
    trace = T.Trace(db, user, conversation_id)
    today = campus_today()
    intent = understand(db, user, text, today, earlier, trace)
    reply = Reply(intent)
    reply.page = page
    if not intent.workflow:
        reply.status = "needs_info"
        reply.say(HELP)
        label, _keys = page_focus(page)
        reply.choices = [{"label": "What needs attention" + (" here" if label else ""),
                          "text": "What needs attention" + (" on this screen?" if label else " today?")},
                         {"label": "Plan and procure", "text": "Plan tomorrow's lunch and tell me what to buy"},
                         {"label": "Explain spending", "text": "Why did spending change this month?"},
                         {"label": "Stock difference", "text": "Investigate a stock count difference"}]
        return reply, trace
    try:
        if intent.workflow == "attention":
            attention(trace, reply, page)
        elif intent.workflow == "plan_procure":
            plan_procure(trace, reply, today)
        elif intent.workflow == "explain_spending":
            explain_spending(trace, reply, today)
        else:
            stock_difference(trace, reply, today, text)
    except T.ToolDenied:
        deny(reply, "the records this needs")
    except HTTPException as exc:
        reply.status = "error"
        reply.say(f"The application refused this step: {exc.detail}")
    trace.record("plan", "reply", {"workflow": intent.workflow}, {"status": reply.status,
                                                                     "proposals": len(reply.proposals)})
    return reply, trace

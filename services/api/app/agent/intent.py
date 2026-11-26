"""Understanding a request (Stage 12).

Two readers produce the same structured Intent:
- RuleReader (always available, no network): workflow keywords, dates
  ("tomorrow", "Friday", "2026-11-30", "this month", "last month",
  "November"), headcount ("for 450 people"), and the campus's own meal
  session, menu and item names.
- GeminiReader (only with AGENT_ENABLED and GEMINI_API_KEY): the model reads
  the request and returns JSON. It receives only the request text, today's
  date and the campus's session, menu and item names; never supplier
  details, money, stock or people. Its output is validated and mapped to
  ids locally; any failure falls back to RuleReader.

Names are matched to records of the user's campus only.
"""

import calendar
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.master_data import Item, MealSession, Menu
from app.models.user import User

WORKFLOWS = ("plan_procure", "explain_spending", "stock_difference")
WEEKDAYS = [d.lower() for d in calendar.day_name]
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})

SPEND = ("spend", "spent", "spending", "expenditure", "expense", "cost more", "costs", "bills went", "price")
STOCK = ("count", "counted", "difference", "below the system", "above the system", "short", "shortage", "missing",
         "discrepan", "variance", "mismatch", "physical", "investigate", "adjust")
PLAN = ("plan", "buy", "procure", "purchase", "order", "need for", "people", "persons", "pax", "cook", "prepare")


@dataclass
class Intent:
    workflow: str | None = None
    plan_date: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    compare: str = "elapsed"
    headcount: int | None = None
    meal_session_id: int | None = None
    menu_id: int | None = None
    item_id: int | None = None
    reader: str = "rules"
    notes: list[str] = field(default_factory=list)

    def merge(self, earlier: dict | None) -> "Intent":
        """Fills gaps from the previous turn (answers to a clarification)."""
        if not earlier:
            return self
        for key, value in earlier.items():
            if key in ("reader", "notes"):
                continue
            if getattr(self, key, None) in (None, "elapsed") and value not in (None, ""):
                if key == "compare" and self.compare != "elapsed":
                    continue
                setattr(self, key, value)
        return self

    def as_dict(self) -> dict:
        return asdict(self)


def norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9/\-\s]", " ", text.lower()) + " "


def best_name(text: str, rows: list[tuple[int, str]]) -> int | None:
    """The longest campus name found in the text (whole words)."""
    hits = [(len(name), rid) for rid, name in rows if name and f" {norm(name).strip()} " in text]
    return max(hits)[1] if hits else None


def month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def read_dates(text: str, today: date) -> dict:
    out: dict = {}
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", text):
        out["day"] = date(int(m[1]), int(m[2]), int(m[3]))
    elif m := re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text):
        out["day"] = date(int(m[3]), int(m[2]), int(m[1]))
    elif " day after tomorrow " in text:
        out["day"] = today + timedelta(days=2)
    elif " tomorrow " in text:
        out["day"] = today + timedelta(days=1)
    elif " today " in text or " tonight " in text:
        out["day"] = today
    elif " yesterday " in text:
        out["day"] = today - timedelta(days=1)
    else:
        for i, name in enumerate(WEEKDAYS):
            if f" {name} " in text:
                ahead = (i - today.weekday()) % 7 or 7
                out["day"] = today + timedelta(days=ahead)
                break
    # "this month compared with last month" is about this month.
    if " this month " in text:
        out["range"] = (today.replace(day=1), today)
    elif " last month " in text or " previous month " in text:
        first = today.replace(day=1) - timedelta(days=1)
        out["range"] = month_range(first.year, first.month)
        out["compare"] = "full"
    elif " this week " in text:
        out["range"] = (today - timedelta(days=today.weekday()), today)
        out["compare"] = "previous"
    elif " last week " in text:
        start = today - timedelta(days=today.weekday() + 7)
        out["range"] = (start, start + timedelta(days=6))
        out["compare"] = "previous"
    else:
        for name, number in MONTHS.items():
            if len(name) >= 3 and f" {name} " in text:
                year = today.year if number <= today.month else today.year - 1
                start, end = month_range(year, number)
                out["range"] = (start, min(end, today))
                out["compare"] = "full" if end < today else "elapsed"
                break
    return out


def campus_names(db: Session, user: User) -> dict:
    campus = user.campus_id
    return {
        "sessions": [(s.id, s.name) for s in db.query(MealSession).filter(
            MealSession.campus_id == campus, MealSession.is_active.is_(True))],
        "menus": [(m.id, m.name, m.meal_session_id) for m in db.query(Menu).filter(
            Menu.campus_id == campus, Menu.is_active.is_(True))],
        "items": [(i.id, i.name) for i in db.query(Item).filter(Item.campus_id == campus, Item.is_active.is_(True))],
    }


def rule_read(text_raw: str, today: date, names: dict) -> Intent:
    text = norm(text_raw)
    intent = Intent()
    scores = {
        "explain_spending": sum(k in text for k in SPEND),
        "stock_difference": sum(k in text for k in STOCK),
        "plan_procure": sum(k in text for k in PLAN),
    }
    if " why " in text and scores["explain_spending"]:
        scores["explain_spending"] += 2
    if re.search(r"\b\d+(\.\d+)?\s*(kg|g|l|ml|pcs|pieces)\b.*\b(below|above|short|less|more)\b", text):
        scores["stock_difference"] += 2
    top = max(scores, key=scores.get)
    intent.workflow = top if scores[top] else None

    dates = read_dates(text, today)
    if "day" in dates:
        intent.plan_date = dates["day"].isoformat()
    if "range" in dates:
        intent.date_from, intent.date_to = (d.isoformat() for d in dates["range"])
        intent.compare = dates.get("compare", "elapsed")
    if " compared with the same days " in text or " same days " in text:
        intent.compare = "elapsed"
    if m := re.search(r"\b(\d{1,6})\s*(people|persons|pax|students|heads|head count|headcount|guests|diners)\b", text):
        intent.headcount = int(m[1])
    elif m := re.search(r"\b(headcount|head count) (of )?(\d{1,6})\b", text):
        intent.headcount = int(m[3])

    intent.meal_session_id = best_name(text, [(i, n) for i, n in names["sessions"]])
    menus = [(i, n) for i, n, s in names["menus"] if not intent.meal_session_id or s == intent.meal_session_id]
    intent.menu_id = best_name(text, menus)
    intent.item_id = best_name(text, names["items"])
    if intent.menu_id and not intent.meal_session_id:
        intent.meal_session_id = next(s for i, _n, s in names["menus"] if i == intent.menu_id)
    return intent


# ============================================================
# OPTIONAL EXTERNAL MODEL
# ============================================================

def llm_available() -> bool:
    return bool(settings.AGENT_ENABLED and settings.GEMINI_API_KEY)


PROMPT = """You read requests to a kitchen management assistant and return JSON only.
Today is {today}. Fields (use null when not stated):
workflow: one of "plan_procure" (plan a meal and what to buy), "explain_spending" (why spending changed),
  "stock_difference" (a physical count differs from the system), or null;
plan_date: YYYY-MM-DD for a meal or count date; date_from, date_to: YYYY-MM-DD for a spending period;
compare: "elapsed" (same days earlier), "full" (whole months) or "previous" (equal period before);
headcount: integer; meal_session, menu, item: copy EXACTLY one name from these lists or null.
Meal sessions: {sessions}
Menus: {menus}
Items: {items}
Request: {request}"""


def gemini_read(text: str, today: date, names: dict) -> Intent:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY,
                          http_options=types.HttpOptions(timeout=int(settings.AGENT_LLM_TIMEOUT_SECONDS * 1000)))
    prompt = PROMPT.format(today=today.isoformat(), request=text[:1000],
                           sessions=json.dumps([n for _i, n in names["sessions"]]),
                           menus=json.dumps([n for _i, n, _s in names["menus"]]),
                           items=json.dumps([n for _i, n in names["items"]][:400]))
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL, contents=prompt,
        config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"))
    data = json.loads(response.text or "{}")
    intent = Intent(reader="gemini")
    if data.get("workflow") in WORKFLOWS:
        intent.workflow = data["workflow"]
    for key in ("plan_date", "date_from", "date_to"):
        try:
            intent.__setattr__(key, date.fromisoformat(str(data.get(key))).isoformat() if data.get(key) else None)
        except ValueError:
            pass
    if data.get("compare") in ("elapsed", "full", "previous"):
        intent.compare = data["compare"]
    if isinstance(data.get("headcount"), int) and 0 < data["headcount"] <= 100000:
        intent.headcount = data["headcount"]

    def lookup(rows, value):
        value = (value or "").strip().lower()
        return next((r[0] for r in rows if r[1].lower() == value), None) if value else None

    intent.meal_session_id = lookup(names["sessions"], data.get("meal_session"))
    intent.menu_id = lookup(names["menus"], data.get("menu"))
    intent.item_id = lookup(names["items"], data.get("item"))
    return intent


def understand(db: Session, user: User, text: str, today: date, earlier: dict | None, trace) -> Intent:
    names = campus_names(db, user)
    rules = rule_read(text, today, names)
    intent = rules
    if llm_available():
        try:
            intent = gemini_read(text, today, names)
            # Rules fill anything the model left out.
            for key, value in rules.as_dict().items():
                if key not in ("reader", "notes", "compare") and getattr(intent, key) is None and value is not None:
                    setattr(intent, key, value)
            trace.record("llm", "gemini_read", {"model": settings.GEMINI_MODEL}, {"intent": intent.as_dict()})
        except Exception as exc:  # network, quota, bad JSON: fall back safely
            trace.record("llm", "gemini_read", {"model": settings.GEMINI_MODEL},
                         {"error": type(exc).__name__, "fallback": "rules"}, ok=False)
            intent = rules
            intent.notes.append("The external AI model was unavailable, so the request was read with the built-in rules.")
    intent.merge(earlier if (earlier and (not intent.workflow or intent.workflow == earlier.get("workflow"))) else None)
    trace.record("understand", "read_request", {"text": text[:500]}, {"intent": intent.as_dict()})
    return intent

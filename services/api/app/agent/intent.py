"""Understanding a request (Stage 12).

Two readers produce the same structured Intent:
- RuleReader (always available, no network): workflow keywords, dates
  ("tomorrow", "Friday", "2026-11-30", "30 November", "Nov 30", "30/11",
  "this month", "last month", "November"), headcount ("for 450 people",
  or "for 450" in a planning request), and the campus's own meal session,
  menu, item and category names.
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
from app.models.master_data import Category, Item, MealSession, Menu
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
    category_id: int | None = None
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
    """The longest campus name found in the text (whole words). Among equally
    long matches, the one listed last in `rows` wins."""
    hits = [(len(name), order, rid) for order, (rid, name) in enumerate(rows)
            if name and f" {norm(name).strip()} " in text]
    return max(hits)[2] if hits else None


def month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def nearest_year(today: date, month: int, day: int) -> date | None:
    """A day and month without a year: this year, or next year when this
    year's date is more than six months past (planning looks ahead)."""
    found = safe_date(today.year, month, day)
    if found and (today - found).days > 183:
        found = safe_date(today.year + 1, month, day)
    return found


MONTH_WORDS = "|".join(sorted((m for m in MONTHS if len(m) >= 3), key=len, reverse=True))


def day_and_month(text: str, today: date) -> date | None:
    """'30 november', '30th nov', 'november 30', 'nov 30th', '30/11', '30-11'."""
    if m := re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTH_WORDS})\b(?:\s+(\d{{4}}))?", text):
        day, month, year = int(m[1]), MONTHS[m[2]], m[3]
    elif m := re.search(rf"\b({MONTH_WORDS})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:\s+(\d{{4}}))?", text):
        day, month, year = int(m[2]), MONTHS[m[1]], m[3]
    elif m := re.search(r"(?<![\d/-])(\d{1,2})[/-](\d{1,2})(?![\d/-])", text):
        day, month, year = int(m[1]), int(m[2]), None
    else:
        return None
    if not 1 <= month <= 12:
        return None
    return safe_date(int(year), month, day) if year else nearest_year(today, month, day)


def all_days(text: str, today: date) -> list[date]:
    """Every day-and-month date in the text, in order ('1 nov to 15 nov')."""
    found = []
    pattern = (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTH_WORDS})\b"
               rf"|\b({MONTH_WORDS})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b")
    for m in re.finditer(pattern, text):
        day, month = (int(m[1]), MONTHS[m[2]]) if m[1] else (int(m[4]), MONTHS[m[3]])
        if (d := nearest_year(today, month, day)) is not None:
            found.append(d)
    return found


def read_dates(text: str, today: date) -> dict:
    out: dict = {}
    days = all_days(text, today)
    if len(days) >= 2 and days[0] <= days[1]:
        # An explicit period: compared with the same length just before it.
        out["range"] = (days[0], min(days[1], today))
        out["compare"] = "previous"
        return out
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", text):
        found = safe_date(int(m[1]), int(m[2]), int(m[3]))
        if found:
            out["day"] = found
    elif m := re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text):
        found = safe_date(int(m[3]), int(m[2]), int(m[1]))
        if found:
            out["day"] = found
    elif found := day_and_month(text, today):
        out["day"] = found
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
    elif "day" not in out or not day_and_month(text, today):
        # A month on its own ("spending in October"); "30 November" is a day.
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
        "categories": [(c.id, c.name) for c in db.query(Category).filter(
            Category.campus_id == campus, Category.is_active.is_(True))],
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
    elif intent.workflow == "plan_procure" and (
            m := re.search(r"\bfor (\d{1,6})\b(?!\s*(?:kg|g|l|ml|pcs|pieces|rs|rupees|days?|weeks?|st|nd|rd|th|/|-))", text)):
        number = int(m[1])
        if not (1900 <= number <= 2100):  # "for 2027" is a year, not people
            intent.headcount = number

    # Duplicate session names differing only in case ("Breakfast" and
    # "breakfast", open question C5): prefer one that has an active menu.
    with_menus = {s for _i, _n, s in names["menus"]}
    sessions = sorted(names["sessions"], key=lambda row: (row[0] in with_menus, -row[0]))
    intent.meal_session_id = best_name(text, sessions)
    menus = [(i, n) for i, n, s in names["menus"] if not intent.meal_session_id or s == intent.meal_session_id]
    intent.menu_id = best_name(text, menus)
    intent.item_id = best_name(text, names["items"])
    intent.category_id = best_name(text, names.get("categories", []))
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
            # The model sees session, menu and item names only (categories
            # are matched by the built-in rules below).
            intent = gemini_read(text, today, {key: names[key] for key in ("sessions", "menus", "items")})
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

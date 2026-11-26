"""The campus-local business date.

Servers usually run on UTC (the Docker image does), while the campuses
work in local time. Between midnight and 05:30 in India the UTC date is
still yesterday, so "today" taken from the server clock would reject a
payment dated today and put the day's figures on the wrong date.
"""

from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

# Used only when the host has no time zone database (slim images without
# tzdata). Asia/Kolkata has no daylight saving, so a fixed offset is exact.
_FIXED_ZONES = {
    "Asia/Kolkata": timezone(timedelta(hours=5, minutes=30), "IST"),
    "Asia/Calcutta": timezone(timedelta(hours=5, minutes=30), "IST"),
    "UTC": timezone.utc,
}


def campus_timezone(name: str | None = None) -> tzinfo:
    name = name or settings.APP_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        if name in _FIXED_ZONES:
            return _FIXED_ZONES[name]
        raise


def campus_today(now: datetime | None = None) -> date:
    """Today's date in the campus time zone. `now` is for tests."""
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(campus_timezone()).date()


def utc_iso(moment: datetime) -> str:
    """An ISO timestamp that always carries its offset, so a browser shows it
    in local time. Stored times are UTC; a driver that drops the zone (SQLite)
    would otherwise be read as local time."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.isoformat()

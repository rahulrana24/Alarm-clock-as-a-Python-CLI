"""Parsing and formatting of times and repeat days typed by the user."""

from __future__ import annotations

from datetime import datetime, time

from alarm_clock.errors import InvalidDays, InvalidTime
from alarm_clock.models import DAY_NAMES, EVERY_DAY, WEEKDAYS, WEEKENDS

# Tried in order. Add a format here to accept a new spelling.
ACCEPTED_FORMATS = (
    "%H:%M",  # 07:30, 19:05
    "%I:%M%p",  # 7:30am, 7:30PM
    "%I:%M %p",  # 7:30 am
    "%I%p",  # 7am
    "%I %p",  # 7 am
)

DAY_ALIASES: dict[str, frozenset[int]] = {
    "daily": EVERY_DAY,
    "everyday": EVERY_DAY,
    "weekdays": WEEKDAYS,
    "weekends": WEEKENDS,
}

_LOWER_DAY_NAMES = tuple(name.lower() for name in DAY_NAMES)


def parse_time(raw: str) -> time:
    text = raw.strip()
    for fmt in ACCEPTED_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise InvalidTime(raw)


def parse_days(raw: str) -> frozenset[int]:
    """Accept an alias (daily, weekdays, weekends) or a comma-separated list
    of day names, full or abbreviated to three letters (mon, Tuesday, ...)."""
    text = raw.strip().lower()
    if text in DAY_ALIASES:
        return DAY_ALIASES[text]
    days: set[int] = set()
    for part in text.split(","):
        key = part.strip()[:3]
        if len(key) < 3 or key not in _LOWER_DAY_NAMES:
            raise InvalidDays(raw)
        days.add(_LOWER_DAY_NAMES.index(key))
    return frozenset(days)


def format_days(days: frozenset[int]) -> str:
    for alias in ("daily", "weekdays", "weekends"):
        if days == DAY_ALIASES[alias]:
            return alias
    return ",".join(DAY_NAMES[day] for day in sorted(days))


def format_time(value: time) -> str:
    return value.strftime("%H:%M")


def format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def format_next(value: datetime, now: datetime) -> str:
    """Short relative wording for list output: '07:30 today', 'Tue 07:30'."""
    clock = value.strftime("%H:%M")
    delta_days = (value.date() - now.date()).days
    if delta_days == 0:
        return f"{clock} today"
    if delta_days == 1:
        return f"{clock} tomorrow"
    return f"{value.strftime('%a')} {clock}"

"""Turn what a human types into times, durations and day sets. No IO, no clock."""

from __future__ import annotations

import re
from datetime import time, timedelta

from .models import ALL_DAYS, DAY_NAMES, WEEKDAYS, WEEKENDS


class TimeParseError(ValueError):
    pass


# 7, 07, 7:30, 07:30, 7pm, 7:30pm, 7:30 PM
_TIME_OF_DAY = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.IGNORECASE)

# +10m, +90, +1h, +1h30m, +1h30
_RELATIVE = re.compile(r"^\+(?:(\d+)h)?(?:(\d+)m?)?$", re.IGNORECASE)

MAX_RELATIVE = timedelta(hours=24)


def is_relative(text: str) -> bool:
    return text.strip().startswith("+")


def parse_time_of_day(text: str) -> time:
    """'7:30pm' -> time(19, 30). A bare hour without am/pm is rejected as ambiguous."""
    raw = text.strip()
    match = _TIME_OF_DAY.match(raw)
    if not match:
        raise TimeParseError(f"'{text}' is not a time; try 07:30, 7:30pm or 7am")

    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) is not None else 0
    meridiem = (match.group(3) or "").lower()

    if meridiem:
        if not 1 <= hour <= 12:
            raise TimeParseError(f"'{text}': hour must be 1-12 with am/pm")
        if meridiem == "am" and hour == 12:
            hour = 0
        elif meridiem == "pm" and hour != 12:
            hour += 12
    elif match.group(2) is None:
        raise TimeParseError(f"'{text}' is ambiguous; say {raw}am, {raw}pm or {int(raw):02d}:00")

    if not 0 <= hour <= 23:
        raise TimeParseError(f"'{text}': hour must be 0-23")
    if not 0 <= minute <= 59:
        raise TimeParseError(f"'{text}': minute must be 0-59")
    return time(hour, minute)


def parse_relative(text: str) -> timedelta:
    """'+1h30m' -> 1h30m. Must be positive and under 24 hours."""
    raw = text.strip().replace(" ", "")
    match = _RELATIVE.match(raw)
    if not match or (match.group(1) is None and match.group(2) is None):
        raise TimeParseError(f"'{text}' is not a duration; try +10m, +90m or +1h30m")
    delta = timedelta(hours=int(match.group(1) or 0), minutes=int(match.group(2) or 0))
    if delta <= timedelta(0):
        raise TimeParseError("duration must be positive")
    if delta >= MAX_RELATIVE:
        raise TimeParseError("relative alarms must be under 24h; set a time of day instead")
    return delta


_PRESETS = {
    "once": [],
    "none": [],
    "daily": ALL_DAYS,
    "everyday": ALL_DAYS,
    "weekdays": WEEKDAYS,
    "weekends": WEEKENDS,
}


def parse_repeat(text: str | None) -> list[int]:
    """'weekdays' -> [0..4]; 'mon,wed,fri' -> [0, 2, 4]; None/'once' -> []."""
    if text is None:
        return []
    key = text.strip().lower()
    if key in _PRESETS:
        return list(_PRESETS[key])
    days: set[int] = set()
    for part in key.split(","):
        part = part.strip()[:3]
        if part not in DAY_NAMES:
            raise TimeParseError(
                f"'{text}' is not a repeat; try daily, weekdays, weekends or mon,wed,fri"
            )
        days.add(DAY_NAMES.index(part))
    return sorted(days)

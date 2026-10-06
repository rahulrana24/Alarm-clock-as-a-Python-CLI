"""Pure scheduling maths. Every function takes the current instant as an argument."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from .models import Alarm


def next_occurrence(at: time, days: list[int], after: datetime) -> datetime:
    """First instant strictly after `after` whose wall-clock time is `at`
    and whose weekday is in `days` (any day when `days` is empty)."""
    base = after.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    for offset in range(8):  # today plus a full week covers every day set
        candidate = base + timedelta(days=offset)
        if candidate <= after:
            continue
        if not days or candidate.weekday() in days:
            return candidate
    raise RuntimeError(f"no occurrence found for {at} on days {days}")  # unreachable


def first_fire_for(alarm: Alarm, now: datetime) -> datetime:
    return next_occurrence(time(alarm.hour, alarm.minute), alarm.days, now)


def snooze(alarm: Alarm, now: datetime) -> None:
    """Transition: ring again in `snooze_minutes`."""
    alarm.next_fire = now.replace(microsecond=0) + timedelta(minutes=alarm.snooze_minutes)
    alarm.snoozed = True


def settle(alarm: Alarm, now: datetime) -> None:
    """Transition after a dismiss (or a give-up): repeating alarms move to the
    next occurrence, one-shot alarms switch off."""
    alarm.snoozed = False
    alarm.auto_snoozes = 0
    if alarm.is_repeating:
        alarm.next_fire = first_fire_for(alarm, now)
    else:
        alarm.enabled = False
        alarm.next_fire = None


def describe_delta(delta: timedelta) -> str:
    """'in 2h 15m', 'in 30s', '3m ago'."""
    seconds = int(delta.total_seconds())
    past = seconds < 0
    seconds = abs(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        text = f"{days}d {hours}h"
    elif hours:
        text = f"{hours}h {minutes}m"
    elif minutes:
        text = f"{minutes}m"
    else:
        text = f"{secs}s"
    return f"{text} ago" if past else f"in {text}"

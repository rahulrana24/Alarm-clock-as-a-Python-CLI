"""The Alarm entity and the rules that decide when it rings.

All time-dependent logic takes ``now`` as an explicit argument. Nothing in
this module reads the system clock, which keeps the rules deterministic and
trivial to unit-test.

An alarm fires at ``ring_at`` on each of its ``days`` (weekday numbers, Monday
is 0). Each such day has one "occurrence" of the alarm. An occurrence keeps
ringing from ``ring_at`` until the user dismisses it, or until it is snoozed,
in which case it rings again at ``snoozed_until``. A ``once`` alarm switches
itself off after its first dismissal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any

ISO_TIME = "%H:%M"

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
EVERY_DAY = frozenset(range(7))
WEEKDAYS = frozenset(range(5))
WEEKENDS = frozenset({5, 6})


class AlarmState(str, Enum):
    """What an alarm is doing at a given instant."""

    INACTIVE = "inactive"  # switched off, will never ring
    SCHEDULED = "scheduled"  # waiting for its next occurrence
    SNOOZED = "snoozed"  # was ringing, will ring again at snoozed_until
    RINGING = "ringing"  # ringing now, waiting to be snoozed or dismissed


@dataclass(slots=True)
class Alarm:
    id: int
    label: str
    ring_at: time
    days: frozenset[int] = EVERY_DAY
    once: bool = False
    is_active: bool = True
    # Absolute instant the alarm rings again after a snooze. None when not snoozed.
    snoozed_until: datetime | None = None
    # Date of the occurrence that was last dismissed. An occurrence rings only
    # if its date differs from this, so a dismissed alarm stays quiet until the
    # next occurrence.
    dismissed_on: date | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        self.days = frozenset(self.days)
        if not self.days or not self.days <= EVERY_DAY:
            raise ValueError("days must be a non-empty set of weekday numbers 0..6")

    # ---- ringing rules -------------------------------------------------

    def due_occurrence_on(self, now: datetime) -> date:
        """Date of the most recent occurrence at or before ``now``.

        At 06:00 an alarm set for 07:00 has not fired today yet, so its most
        recent occurrence is an earlier day's. At 08:00 it is today's, if
        today is one of the alarm's days.
        """
        candidate = now.date()
        if now.time() < self.ring_at:
            candidate -= timedelta(days=1)
        while candidate.weekday() not in self.days:
            candidate -= timedelta(days=1)
        return candidate

    def is_ringing(self, now: datetime) -> bool:
        if not self.is_active:
            return False
        if self.snoozed_until is not None:
            return now >= self.snoozed_until
        return self.dismissed_on != self.due_occurrence_on(now)

    def state(self, now: datetime) -> AlarmState:
        if not self.is_active:
            return AlarmState.INACTIVE
        if self.is_ringing(now):
            return AlarmState.RINGING
        if self.snoozed_until is not None:
            return AlarmState.SNOOZED
        return AlarmState.SCHEDULED

    def next_ring_at(self, now: datetime) -> datetime | None:
        """When the alarm will ring (or started ringing). None if inactive."""
        if not self.is_active:
            return None
        if self.snoozed_until is not None:
            return self.snoozed_until
        if self.is_ringing(now):
            return datetime.combine(self.due_occurrence_on(now), self.ring_at)
        for offset in range(8):
            day = now.date() + timedelta(days=offset)
            candidate = datetime.combine(day, self.ring_at)
            if candidate > now and day.weekday() in self.days:
                return candidate
        return None  # unreachable: days is never empty

    # ---- state transitions ---------------------------------------------
    # These mutate the alarm. The service decides *when* they may be called.

    def activate(self, now: datetime) -> None:
        """Switch on. The alarm first rings at its next occurrence, never
        retroactively for a time that already passed today."""
        self.is_active = True
        self.snoozed_until = None
        self.dismissed_on = self.due_occurrence_on(now)

    def deactivate(self) -> None:
        self.is_active = False
        self.snoozed_until = None

    def snooze(self, now: datetime, duration: timedelta) -> None:
        self.snoozed_until = now + duration

    def dismiss(self, now: datetime) -> None:
        """Silence the current occurrence until the next one."""
        self.snoozed_until = None
        self.dismissed_on = self.due_occurrence_on(now)
        if self.once:
            self.is_active = False

    # ---- serialisation -------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "ring_at": self.ring_at.strftime(ISO_TIME), # nextFire
            "days": sorted(self.days),
            "once": self.once,
            "is_active": self.is_active,
            "snoozed_until": _iso_or_none(self.snoozed_until),
            "dismissed_on": _iso_or_none(self.dismissed_on),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Alarm:
        return cls(
            id=int(data["id"]),
            label=str(data["label"]),
            ring_at=datetime.strptime(data["ring_at"], ISO_TIME).time(),
            days=frozenset(data.get("days", EVERY_DAY)),
            once=bool(data.get("once", False)),
            is_active=bool(data.get("is_active", True)),
            snoozed_until=_parse_or_none(datetime.fromisoformat, data.get("snoozed_until")),
            dismissed_on=_parse_or_none(date.fromisoformat, data.get("dismissed_on")),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


def _iso_or_none(value: date | datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _parse_or_none(parse, raw: str | None):
    return None if raw is None else parse(raw)

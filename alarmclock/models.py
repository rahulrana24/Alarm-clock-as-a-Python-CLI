"""The Alarm record and its (de)serialisation. No IO, no clock access."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

ALL_DAYS = list(range(7))
WEEKDAYS = list(range(5))
WEEKENDS = [5, 6]


class AlarmNotFound(LookupError):
    pass


class AmbiguousAlarmId(LookupError):
    pass


def new_id() -> str:
    """Short ids are typed by humans; four hex chars is plenty for one person."""
    return uuid.uuid4().hex[:4]


@dataclass
class Alarm:
    id: str
    hour: int
    minute: int
    label: str = ""
    days: list[int] = field(default_factory=list)  # Python weekday numbers; [] = one-shot
    enabled: bool = True
    snooze_minutes: int = 5
    next_fire: datetime | None = None
    snoozed: bool = False
    auto_snoozes: int = 0

    # -- derived -----------------------------------------------------------

    @property
    def is_repeating(self) -> bool:
        return bool(self.days)

    @property
    def time_str(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"

    @property
    def repeat_str(self) -> str:
        return describe_days(self.days)

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hour": self.hour,
            "minute": self.minute,
            "label": self.label,
            "days": list(self.days),
            "enabled": self.enabled,
            "snooze_minutes": self.snooze_minutes,
            "next_fire": self.next_fire.isoformat() if self.next_fire else None,
            "snoozed": self.snoozed,
            "auto_snoozes": self.auto_snoozes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Alarm":
        raw_next = data.get("next_fire")
        return cls(
            id=str(data["id"]),
            hour=int(data["hour"]),
            minute=int(data["minute"]),
            label=str(data.get("label", "")),
            days=sorted(int(d) for d in data.get("days", [])),
            enabled=bool(data.get("enabled", True)),
            snooze_minutes=int(data.get("snooze_minutes", 5)),
            next_fire=datetime.fromisoformat(raw_next) if raw_next else None,
            snoozed=bool(data.get("snoozed", False)),
            auto_snoozes=int(data.get("auto_snoozes", 0)),
        )


def describe_days(days: Iterable[int]) -> str:
    days = sorted(set(days))
    if not days:
        return "once"
    if days == ALL_DAYS:
        return "daily"
    if days == WEEKDAYS:
        return "weekdays"
    if days == WEEKENDS:
        return "weekends"
    return ",".join(DAY_LABELS[d] for d in days)


def find_alarm(alarms: list[Alarm], id_prefix: str) -> Alarm:
    """Resolve a user-typed id, allowing a unique prefix."""
    id_prefix = id_prefix.strip().lower()
    if not id_prefix:
        raise AlarmNotFound("empty id")
    exact = [a for a in alarms if a.id == id_prefix]
    if exact:
        return exact[0]
    matches = [a for a in alarms if a.id.startswith(id_prefix)]
    if not matches:
        raise AlarmNotFound(f"no alarm with id '{id_prefix}'")
    if len(matches) > 1:
        ids = ", ".join(a.id for a in matches)
        raise AmbiguousAlarmId(f"'{id_prefix}' matches several alarms: {ids}")
    return matches[0]

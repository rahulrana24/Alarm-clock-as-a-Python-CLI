"""Use cases of the alarm clock.

``AlarmService`` is the single entry point for anything that changes alarms.
It owns ID assignment, enforces the rules (for example "only a ringing alarm
can be snoozed") and persists through an ``AlarmRepository``.

The clock is injected so tests can freeze time.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timedelta

from alarm_clock.errors import AlarmNotFound, AlarmNotRinging
from alarm_clock.models import EVERY_DAY, Alarm
from alarm_clock.repository import AlarmRepository

Clock = Callable[[], datetime]

DEFAULT_SNOOZE = timedelta(minutes=5)


class AlarmService:
    def __init__(self, repository: AlarmRepository, clock: Clock = datetime.now) -> None:
        self._repository = repository
        self._clock = clock

    # ---- queries -------------------------------------------------------

    def now(self) -> datetime:
        return self._clock()

    def list_alarms(self) -> list[Alarm]:
        return sorted(self._repository.load(), key=lambda alarm: alarm.id)

    def get(self, alarm_id: int) -> Alarm:
        return _find(self._repository.load(), alarm_id)

    def ringing(self) -> list[Alarm]:
        now = self.now()
        return [alarm for alarm in self.list_alarms() if alarm.is_ringing(now)]

    # ---- commands ------------------------------------------------------

    def create(
        self,
        ring_at: time,
        label: str = "",
        days: frozenset[int] = EVERY_DAY,
        once: bool = False,
    ) -> Alarm:
        alarms = self._repository.load()
        alarm = Alarm(id=self._next_id(alarms), label=label, ring_at=ring_at, days=days, once=once)
        alarm.activate(self.now())
        alarms.append(alarm)
        self._repository.save(alarms)
        return alarm

    def update(
        self,
        alarm_id: int,
        *,
        ring_at: time | None = None,
        label: str | None = None,
        days: frozenset[int] | None = None,
        once: bool | None = None,
    ) -> Alarm:
        """Change any subset of an alarm's settings. Changing when it rings
        resets its schedule so it never fires retroactively."""
        now = self.now()

        def apply(alarm: Alarm) -> None:
            schedule_changed = False
            if ring_at is not None and ring_at != alarm.ring_at:
                alarm.ring_at = ring_at
                schedule_changed = True
            if days is not None and days != alarm.days:
                alarm.days = frozenset(days)
                schedule_changed = True
            if label is not None:
                alarm.label = label
            if once is not None:
                alarm.once = once
            if schedule_changed and alarm.is_active:
                alarm.activate(now)

        return self._update(alarm_id, apply)

    def delete(self, alarm_id: int) -> Alarm:
        alarms = self._repository.load()
        alarm = _find(alarms, alarm_id)
        alarms.remove(alarm)
        self._repository.save(alarms)
        return alarm

    def activate(self, alarm_id: int) -> Alarm:
        return self._update(alarm_id, lambda alarm: alarm.activate(self.now()))

    def deactivate(self, alarm_id: int) -> Alarm:
        return self._update(alarm_id, lambda alarm: alarm.deactivate())

    def snooze(self, alarm_id: int, duration: timedelta = DEFAULT_SNOOZE) -> Alarm:
        now = self.now()

        def apply(alarm: Alarm) -> None:
            if not alarm.is_ringing(now):
                raise AlarmNotRinging(alarm.id)
            alarm.snooze(now, duration)

        return self._update(alarm_id, apply)

    def dismiss(self, alarm_id: int) -> Alarm:
        return self._update(alarm_id, lambda alarm: alarm.dismiss(self.now()))

    # ---- internals -----------------------------------------------------

    def _update(self, alarm_id: int, apply: Callable[[Alarm], None]) -> Alarm:
        """Load, apply one change to one alarm, save. Every mutation goes
        through here so persistence happens in exactly one place."""
        alarms = self._repository.load()
        alarm = _find(alarms, alarm_id)
        apply(alarm)
        self._repository.save(alarms)
        return alarm

    @staticmethod
    def _next_id(alarms: list[Alarm]) -> int:
        return max((alarm.id for alarm in alarms), default=0) + 1


def _find(alarms: list[Alarm], alarm_id: int) -> Alarm:
    for alarm in alarms:
        if alarm.id == alarm_id:
            return alarm
    raise AlarmNotFound(alarm_id)

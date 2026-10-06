"""The loop that turns stored alarms into actual ringing.

Every ``interval`` seconds the watcher asks the service which alarms ring.
When one starts ringing it announces it (log line + OS notification), keeps
chiming while it rings, and applies whatever the user does through the
reaction sources (snooze, dismiss, quit).

Nothing here reads the system clock directly: time comes from the service
and sleeping is injectable, so the whole loop is unit-testable.
"""

from __future__ import annotations

import signal
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from alarm_clock.errors import AlarmError
from alarm_clock.inputs import Reaction, ReactionSource
from alarm_clock.models import Alarm
from alarm_clock.notify import Notifier
from alarm_clock.service import DEFAULT_SNOOZE, AlarmService
from alarm_clock.timefmt import format_datetime, format_time

POLL_STEP = 0.25  # seconds between input polls; keeps key presses snappy


class Watcher:
    def __init__(
        self,
        service: AlarmService,
        notifier: Notifier,
        sources: Sequence[ReactionSource],
        *,
        interval: float = 5.0,
        chime_every: float = 4.0,
        snooze: timedelta = DEFAULT_SNOOZE,
        out: Callable[[str], None] = print,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._service = service
        self._notifier = notifier
        self._sources = list(sources)
        self._interval = timedelta(seconds=interval)
        self._chime_every = timedelta(seconds=chime_every)
        self._snooze = snooze
        self._out = out
        self._sleep = sleep

        self._ringing: list[Alarm] = []
        self._last_refresh: datetime | None = None
        self._last_chime: datetime | None = None
        self._stopped = False

    # ---- lifecycle -----------------------------------------------------

    def run(self) -> None:
        self._print_banner()
        previous_handler = signal.signal(signal.SIGTERM, lambda *_: self.stop())
        try:
            while not self._stopped:
                self.tick()
                self._sleep(POLL_STEP)
        except KeyboardInterrupt:
            pass
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
            self.close()
            self._out("Stopped watching.")

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        for source in self._sources:
            source.close()
        self._notifier.close()

    # ---- one iteration -------------------------------------------------

    def tick(self) -> None:
        now = self._service.now()
        if self._last_refresh is None or now - self._last_refresh >= self._interval:
            self._refresh(now)
        for source in self._sources:
            reaction = source.poll()
            if reaction is not None:
                self._react(reaction, now)
        if self._ringing and (self._last_chime is None or now - self._last_chime >= self._chime_every):
            self._notifier.chime()
            self._last_chime = now

    def _refresh(self, now: datetime) -> None:
        ringing = self._service.ringing()
        previous_ids = {alarm.id for alarm in self._ringing}
        current_ids = {alarm.id for alarm in ringing}
        if current_ids != previous_ids:
            for alarm in ringing:
                if alarm.id not in previous_ids:
                    self._announce(alarm, now)
            for source in self._sources:
                source.ringing_changed(ringing)
            if not ringing:
                self._notifier.close()
                self._last_chime = None
        self._ringing = ringing
        self._last_refresh = now

    def _announce(self, alarm: Alarm, now: datetime) -> None:
        self._out(f"{format_datetime(now)}  RINGING  {_name(alarm)}")
        self._notifier.notify("Alarm", _name(alarm))

    def _react(self, reaction: Reaction, now: datetime) -> None:
        if reaction is Reaction.QUIT:
            self.stop()
            return
        for alarm in self._ringing:
            try:
                if reaction is Reaction.SNOOZE:
                    updated = self._service.snooze(alarm.id, self._snooze)
                    assert updated.snoozed_until is not None
                    self._out(f"{format_datetime(now)}  snoozed  {_name(alarm)} until {format_datetime(updated.snoozed_until)}")
                else:
                    self._service.dismiss(alarm.id)
                    self._out(f"{format_datetime(now)}  dismissed  {_name(alarm)}")
            except AlarmError as error:  # e.g. already dismissed from another terminal
                self._out(f"{format_datetime(now)}  skipped  {_name(alarm)}: {error}")
        self._refresh(now)

    def _print_banner(self) -> None:
        count = len(self._service.list_alarms())
        self._out(f"Watching {count} alarm(s), checking every {self._interval.total_seconds():g}s. Ctrl+C to stop.")
        for source in self._sources:
            if source.hint:
                self._out(source.hint)


def _name(alarm: Alarm) -> str:
    return f"[{alarm.id}] {alarm.label or 'Alarm'} ({format_time(alarm.ring_at)})"

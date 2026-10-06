"""The long-lived side: tick, find due alarms, ring, apply the outcome.

Clock, sleep, ringer and keyboard are all injected so the whole state machine
runs in tests in milliseconds with no real time passing.
"""

from __future__ import annotations

import queue
import sys
import threading
import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Iterable, Protocol, TextIO

from .models import Alarm, AlarmNotFound
from .ringer import Ringer
from .scheduler import describe_delta, settle, snooze
from .storage import AlarmStore


class RingOutcome(str, Enum):
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"
    TIMED_OUT = "timed out"
    MISSED = "missed"


# -- keyboard --------------------------------------------------------------


class InputSource(Protocol):
    def drain(self) -> None: ...
    def poll(self) -> str | None: ...


class StdinInput:
    """A daemon thread blocks on readline and hands lines to a queue, so the
    ring loop can keep beeping while it waits for a keypress."""

    def __init__(self, stream: TextIO = sys.stdin):
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._pump, args=(stream,), daemon=True)
        self._thread.start()

    def _pump(self, stream: TextIO) -> None:
        try:
            for line in iter(stream.readline, ""):
                self._queue.put(line)
        except (ValueError, OSError):  # stream closed
            pass

    def drain(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def poll(self) -> str | None:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None


class ScriptedInput:
    """Test double: each poll() returns the next scripted item (None = no key)."""

    def __init__(self, lines: Iterable[str | None]):
        self._lines = list(lines)
        self.drained = 0

    def drain(self) -> None:
        self.drained += 1

    def poll(self) -> str | None:
        return self._lines.pop(0) if self._lines else None


# -- state machine ---------------------------------------------------------


@dataclass
class RunnerConfig:
    ring_seconds: int = 60
    grace_seconds: int = 600
    max_auto_snoozes: int = 3
    tick_seconds: float = 1.0


def apply_outcome(alarm: Alarm, outcome: RingOutcome, now: datetime, config: RunnerConfig) -> RingOutcome:
    """Mutate `alarm` for what just happened. Returns the effective outcome
    (a timeout becomes a snooze until the auto-snooze budget is spent)."""
    if outcome is RingOutcome.SNOOZED:
        snooze(alarm, now)
        return RingOutcome.SNOOZED
    if outcome is RingOutcome.TIMED_OUT and alarm.auto_snoozes < config.max_auto_snoozes:
        alarm.auto_snoozes += 1
        snooze(alarm, now)
        return RingOutcome.SNOOZED
    settle(alarm, now)
    return RingOutcome.DISMISSED if outcome is RingOutcome.DISMISSED else RingOutcome.MISSED


class Runner:
    def __init__(
        self,
        store: AlarmStore,
        ringer: Ringer,
        input_source: InputSource,
        clock: Callable[[], datetime] = datetime.now,
        sleep: Callable[[float], None] = _time.sleep,
        out: TextIO = sys.stdout,
        config: RunnerConfig | None = None,
    ):
        self.store = store
        self.ringer = ringer
        self.input = input_source
        self.clock = clock
        self.sleep = sleep
        self.out = out
        self.config = config or RunnerConfig()

    def _say(self, text: str = "") -> None:
        self.out.write(text + "\n")
        self.out.flush()

    # -- loop --------------------------------------------------------------

    def run(self, once: bool = False) -> int:
        self._say(f"Alarm clock running, watching {self.store.path}. Ctrl-C to quit.")
        try:
            while True:
                handled = self.tick()
                if once and handled:
                    return 0
                self.sleep(self.config.tick_seconds)
        except KeyboardInterrupt:
            self._say("\nStopped.")
            return 0

    def tick(self) -> list[tuple[Alarm, RingOutcome]]:
        """Handle every due alarm once. Returns what happened, for tests and --once."""
        now = self.clock()
        due = [
            a for a in self.store.load()
            if a.enabled and a.next_fire is not None and a.next_fire <= now
        ]
        due.sort(key=lambda a: a.next_fire)  # type: ignore[arg-type, return-value]

        handled: list[tuple[Alarm, RingOutcome]] = []
        for alarm in due:
            now = self.clock()
            overdue = now - alarm.next_fire  # type: ignore[operator]
            if overdue > timedelta(seconds=self.config.grace_seconds):
                self._say(
                    f"Missed alarm {alarm.id} ({alarm.time_str} {alarm.label}).".replace("  ", " ")
                    + f" It was due {describe_delta(-overdue)}; the clock was not running."
                )
                outcome = RingOutcome.MISSED
            else:
                outcome = self.ring(alarm)

            after = self.clock()
            try:
                updated = self.store.update(
                    alarm.id, lambda a: apply_outcome(a, outcome, after, self.config)
                )
            except AlarmNotFound:
                self._say(f"Alarm {alarm.id} was removed while it was ringing.")
                handled.append((alarm, outcome))
                continue
            self._report(updated, outcome, after)
            handled.append((updated, outcome))
        return handled

    # -- ringing -----------------------------------------------------------

    def ring(self, alarm: Alarm) -> RingOutcome:
        self.input.drain()  # a stray Enter from earlier must not dismiss this
        start = self.clock()
        deadline = start + timedelta(seconds=self.config.ring_seconds)

        label = f"  {alarm.label}" if alarm.label else ""
        self._say()
        self._say("=" * 48)
        self._say(f"  ALARM  {start:%H:%M}{label}")
        self._say(f"  [Enter] dismiss   [s + Enter] snooze {alarm.snooze_minutes}m")
        self._say("=" * 48)

        while True:
            self.ringer.beep()
            line = self.input.poll()
            if line is not None:
                command = line.strip().lower()
                if command in ("", "d", "dismiss"):
                    return RingOutcome.DISMISSED
                if command in ("s", "snooze"):
                    return RingOutcome.SNOOZED
                self._say("  Enter = dismiss, s = snooze")
            if self.clock() >= deadline:
                return RingOutcome.TIMED_OUT
            self.sleep(self.config.tick_seconds)

    def _report(self, alarm: Alarm, outcome: RingOutcome, now: datetime) -> None:
        if alarm.next_fire is not None and alarm.enabled:
            when = f"next {alarm.next_fire:%a %H:%M} ({describe_delta(alarm.next_fire - now)})"
        else:
            when = "switched off"
        if outcome is RingOutcome.TIMED_OUT and alarm.snoozed:
            verb = f"no answer, auto-snoozed ({alarm.auto_snoozes}/{self.config.max_auto_snoozes})"
        elif outcome is RingOutcome.TIMED_OUT:
            verb = f"no answer {self.config.max_auto_snoozes + 1} times, giving up (missed)"
        else:
            verb = outcome.value
        self._say(f"Alarm {alarm.id}: {verb}; {when}.")

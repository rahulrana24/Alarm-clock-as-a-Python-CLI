"""Tests for the watch loop with a fake clock, notifier and reaction source."""

from __future__ import annotations

import unittest
from collections import deque
from datetime import datetime, time, timedelta

from alarm_clock.inputs import Reaction
from alarm_clock.models import Alarm, AlarmState
from alarm_clock.repository import InMemoryAlarmRepository
from alarm_clock.service import AlarmService
from alarm_clock.watcher import Watcher


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


class SpyNotifier:
    def __init__(self) -> None:
        self.notifications: list[tuple[str, str]] = []
        self.chimes = 0
        self.closed = 0

    def notify(self, title: str, message: str) -> None:
        self.notifications.append((title, message))

    def chime(self) -> None:
        self.chimes += 1

    def close(self) -> None:
        self.closed += 1


class ScriptedSource:
    """Hands out queued reactions and records what it was told."""

    hint = "scripted"

    def __init__(self, *reactions: Reaction) -> None:
        self.reactions = deque(reactions)
        self.ringing_updates: list[list[int]] = []
        self.closed = False

    def ringing_changed(self, alarms: list[Alarm]) -> None:
        self.ringing_updates.append([alarm.id for alarm in alarms])

    def poll(self) -> Reaction | None:
        return self.reactions.popleft() if self.reactions else None

    def close(self) -> None:
        self.closed = True


class WatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock(datetime(2026, 10, 6, 6, 59))
        self.service = AlarmService(InMemoryAlarmRepository(), clock=self.clock)
        self.alarm = self.service.create(time(7, 0), "Gym")
        self.notifier = SpyNotifier()
        self.output: list[str] = []

    def make_watcher(self, *sources) -> Watcher:
        return Watcher(
            self.service, self.notifier, sources, interval=5, chime_every=4, out=self.output.append
        )

    def test_announces_once_and_chimes_while_ringing(self) -> None:
        source = ScriptedSource()
        watcher = self.make_watcher(source)
        watcher.tick()
        self.assertEqual(self.notifier.notifications, [])

        self.clock.now = datetime(2026, 10, 6, 7, 0)
        watcher.tick()
        self.assertEqual(self.notifier.notifications, [("Alarm", "[1] Gym (07:00)")])
        self.assertEqual(self.notifier.chimes, 1)
        self.assertEqual(source.ringing_updates, [[1]])
        self.assertIn("RINGING", self.output[-1])

        self.clock.now += timedelta(seconds=2)
        watcher.tick()
        self.assertEqual(self.notifier.chimes, 1)  # too soon for another chime
        self.clock.now += timedelta(seconds=3)
        watcher.tick()
        self.assertEqual(self.notifier.chimes, 2)
        self.assertEqual(len(self.notifier.notifications), 1)  # never re-announced

    def test_snooze_reaction_snoozes_all_ringing_alarms(self) -> None:
        self.clock.now = datetime(2026, 10, 6, 7, 0)
        source = ScriptedSource(Reaction.SNOOZE)
        self.make_watcher(source).tick()
        alarm = self.service.get(self.alarm.id)
        self.assertEqual(alarm.state(self.clock.now), AlarmState.SNOOZED)
        self.assertEqual(alarm.snoozed_until, datetime(2026, 10, 6, 7, 5))
        self.assertEqual(source.ringing_updates, [[1], []])  # told it stopped ringing
        self.assertEqual(self.notifier.closed, 1)  # sound stopped

    def test_dismiss_reaction(self) -> None:
        self.clock.now = datetime(2026, 10, 6, 7, 0)
        self.make_watcher(ScriptedSource(Reaction.DISMISS)).tick()
        self.assertEqual(self.service.get(self.alarm.id).state(self.clock.now), AlarmState.SCHEDULED)

    def test_quit_reaction_stops_and_closes_everything(self) -> None:
        source = ScriptedSource(Reaction.QUIT)
        self.make_watcher(source).run()
        self.assertTrue(source.closed)
        self.assertEqual(self.notifier.closed, 1)
        self.assertEqual(self.output[-1], "Stopped watching.")

    def test_reaction_when_alarm_already_handled_elsewhere_is_reported_not_fatal(self) -> None:
        self.clock.now = datetime(2026, 10, 6, 7, 0)
        watcher = self.make_watcher(ScriptedSource(Reaction.SNOOZE))
        watcher._refresh(self.clock.now)  # sees it ringing
        self.service.dismiss(self.alarm.id)  # another terminal dismisses it
        watcher.tick()
        self.assertTrue(any("skipped" in line for line in self.output))


if __name__ == "__main__":
    unittest.main()

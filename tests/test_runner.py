"""The ring/snooze/dismiss/timeout/missed state machine, driven by a fake clock."""

import io
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from alarmclock.models import Alarm
from alarmclock.runner import RingOutcome, Runner, RunnerConfig, ScriptedInput
from alarmclock.storage import AlarmStore

T0 = datetime(2026, 10, 6, 7, 0, 0)  # Tuesday


class FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


class CountingRinger:
    def __init__(self):
        self.beeps = 0

    def beep(self):
        self.beeps += 1


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AlarmStore(Path(self.tmp.name) / "alarms.json")
        self.clock = FakeClock(T0)
        self.ringer = CountingRinger()
        self.out = io.StringIO()

    def tearDown(self):
        self.tmp.cleanup()

    def make_runner(self, keys, **config):
        return Runner(
            store=self.store,
            ringer=self.ringer,
            input_source=ScriptedInput(keys),
            clock=self.clock,
            sleep=self.clock.sleep,
            out=self.out,
            config=RunnerConfig(ring_seconds=10, grace_seconds=600, max_auto_snoozes=2, **config),
        )

    def put(self, **kw):
        alarm = Alarm(id="a1", hour=7, minute=0, **kw)
        self.store.save([alarm])
        return alarm

    def loaded(self):
        return self.store.load()[0]

    # -- basics --------------------------------------------------------------

    def test_not_due_means_no_ring(self):
        self.put(next_fire=T0 + timedelta(minutes=1))
        handled = self.make_runner([]).tick()
        self.assertEqual(handled, [])
        self.assertEqual(self.ringer.beeps, 0)

    def test_due_at_exactly_now_fires(self):
        self.put(next_fire=T0)
        handled = self.make_runner([None, ""]).tick()
        self.assertEqual(handled[0][1], RingOutcome.DISMISSED)
        self.assertGreaterEqual(self.ringer.beeps, 1)

    def test_dismiss_one_shot_switches_off(self):
        self.put(next_fire=T0)
        self.make_runner([""]).tick()
        alarm = self.loaded()
        self.assertFalse(alarm.enabled)
        self.assertIsNone(alarm.next_fire)

    def test_dismiss_repeating_reschedules(self):
        self.put(next_fire=T0, days=[0, 1, 2, 3, 4])
        self.make_runner(["d"]).tick()
        alarm = self.loaded()
        self.assertTrue(alarm.enabled)
        self.assertEqual(alarm.next_fire, datetime(2026, 10, 7, 7, 0))

    def test_snooze(self):
        self.put(next_fire=T0, snooze_minutes=5)
        # two ticks of beeping with no key, then "s"
        handled = self.make_runner([None, None, "s\n"]).tick()
        self.assertEqual(handled[0][1], RingOutcome.SNOOZED)
        alarm = self.loaded()
        self.assertTrue(alarm.snoozed)
        self.assertEqual(alarm.next_fire, self.clock.now + timedelta(minutes=5))
        self.assertTrue(alarm.enabled)

    def test_unknown_key_keeps_ringing(self):
        self.put(next_fire=T0)
        handled = self.make_runner(["x", "banana", ""]).tick()
        self.assertEqual(handled[0][1], RingOutcome.DISMISSED)
        self.assertIn("Enter = dismiss", self.out.getvalue())

    # -- timeouts ------------------------------------------------------------

    def test_timeout_auto_snoozes_then_gives_up(self):
        self.put(next_fire=T0, snooze_minutes=1)
        runner = self.make_runner([])

        runner.tick()  # nobody answers: auto-snooze 1/2
        alarm = self.loaded()
        self.assertEqual(alarm.auto_snoozes, 1)
        self.assertTrue(alarm.enabled)
        self.assertGreater(alarm.next_fire, self.clock.now - timedelta(seconds=1))

        self.clock.now = alarm.next_fire
        runner.tick()  # auto-snooze 2/2
        self.assertEqual(self.loaded().auto_snoozes, 2)

        self.clock.now = self.loaded().next_fire
        handled = runner.tick()  # budget spent: give up
        self.assertEqual(handled[0][1], RingOutcome.TIMED_OUT)
        alarm = self.loaded()
        self.assertFalse(alarm.enabled)
        self.assertIn("missed", self.out.getvalue())

    def test_ring_stops_at_deadline(self):
        self.put(next_fire=T0)
        self.make_runner([]).tick()
        # 10 ring seconds at 1s per tick: must not beep for much longer than that
        self.assertLessEqual(self.ringer.beeps, 12)

    # -- grace window --------------------------------------------------------

    def test_overdue_past_grace_is_missed_not_rung(self):
        self.put(next_fire=T0 - timedelta(hours=3), days=[0, 1, 2, 3, 4])
        handled = self.make_runner([]).tick()
        self.assertEqual(handled[0][1], RingOutcome.MISSED)
        self.assertEqual(self.ringer.beeps, 0)
        self.assertEqual(self.loaded().next_fire, datetime(2026, 10, 7, 7, 0))
        self.assertIn("Missed alarm", self.out.getvalue())

    def test_slightly_late_still_rings(self):
        self.put(next_fire=T0 - timedelta(minutes=2))
        handled = self.make_runner([""]).tick()
        self.assertEqual(handled[0][1], RingOutcome.DISMISSED)
        self.assertGreater(self.ringer.beeps, 0)

    # -- concurrency with other writers -------------------------------------

    def test_alarm_added_during_ring_is_kept(self):
        self.put(next_fire=T0)
        runner = self.make_runner([None, None, ""])
        original_ring = runner.ring

        def ring_and_add(alarm):
            # simulate `alarm add` from another terminal while this one rings
            alarms = self.store.load()
            alarms.append(Alarm(id="b2", hour=9, minute=0, next_fire=T0 + timedelta(hours=2)))
            self.store.save(alarms)
            return original_ring(alarm)

        runner.ring = ring_and_add
        runner.tick()
        ids = sorted(a.id for a in self.store.load())
        self.assertEqual(ids, ["a1", "b2"])
        self.assertFalse(next(a for a in self.store.load() if a.id == "a1").enabled)

    def test_alarm_removed_during_ring(self):
        self.put(next_fire=T0)
        runner = self.make_runner([""])
        runner.ring = lambda alarm: (self.store.save([]), RingOutcome.DISMISSED)[1]
        handled = runner.tick()
        self.assertEqual(handled[0][1], RingOutcome.DISMISSED)
        self.assertIn("removed", self.out.getvalue())

    def test_stale_keypress_is_drained(self):
        self.put(next_fire=T0)
        inp = ScriptedInput([""])
        runner = self.make_runner([])
        runner.input = inp
        runner.tick()
        self.assertEqual(inp.drained, 1)

    def test_run_once_exits_after_first_alarm(self):
        self.put(next_fire=T0 + timedelta(seconds=3))
        code = self.make_runner([""]).run(once=True)
        self.assertEqual(code, 0)
        self.assertFalse(self.loaded().enabled)


if __name__ == "__main__":
    unittest.main()

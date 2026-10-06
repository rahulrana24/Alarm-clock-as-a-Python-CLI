import unittest
from datetime import datetime, time, timedelta

from alarmclock.models import Alarm
from alarmclock.scheduler import describe_delta, next_occurrence, settle, snooze

# Tuesday 6 Oct 2026, 09:15:30
NOW = datetime(2026, 10, 6, 9, 15, 30)


class NextOccurrenceTests(unittest.TestCase):
    def test_later_today(self):
        self.assertEqual(next_occurrence(time(10, 0), [], NOW), datetime(2026, 10, 6, 10, 0))

    def test_earlier_today_rolls_to_tomorrow(self):
        self.assertEqual(next_occurrence(time(9, 0), [], NOW), datetime(2026, 10, 7, 9, 0))

    def test_same_minute_is_not_now(self):
        # 09:15 already started (we are at 09:15:30), so the next 09:15 is tomorrow.
        self.assertEqual(next_occurrence(time(9, 15), [], NOW), datetime(2026, 10, 7, 9, 15))

    def test_weekdays_skip_weekend(self):
        friday = datetime(2026, 10, 9, 12, 0)
        self.assertEqual(next_occurrence(time(7, 0), [0, 1, 2, 3, 4], friday), datetime(2026, 10, 12, 7, 0))

    def test_single_day_a_week_away(self):
        # Tuesday 09:15, alarm Tuesdays at 09:00 -> next Tuesday.
        self.assertEqual(next_occurrence(time(9, 0), [1], NOW), datetime(2026, 10, 13, 9, 0))

    def test_single_day_today_later(self):
        self.assertEqual(next_occurrence(time(9, 30), [1], NOW), datetime(2026, 10, 6, 9, 30))


class TransitionTests(unittest.TestCase):
    def test_snooze_sets_next_fire(self):
        alarm = Alarm(id="a", hour=9, minute=0, snooze_minutes=7, next_fire=NOW)
        snooze(alarm, NOW)
        self.assertEqual(alarm.next_fire, NOW + timedelta(minutes=7))
        self.assertTrue(alarm.snoozed)

    def test_settle_one_shot_switches_off(self):
        alarm = Alarm(id="a", hour=9, minute=0, next_fire=NOW, snoozed=True, auto_snoozes=2)
        settle(alarm, NOW)
        self.assertFalse(alarm.enabled)
        self.assertIsNone(alarm.next_fire)
        self.assertFalse(alarm.snoozed)
        self.assertEqual(alarm.auto_snoozes, 0)

    def test_settle_repeating_moves_forward(self):
        alarm = Alarm(id="a", hour=9, minute=0, days=[0, 1, 2, 3, 4], next_fire=NOW)
        settle(alarm, NOW)
        self.assertTrue(alarm.enabled)
        self.assertEqual(alarm.next_fire, datetime(2026, 10, 7, 9, 0))


class DescribeDeltaTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(describe_delta(timedelta(seconds=45)), "in 45s")
        self.assertEqual(describe_delta(timedelta(minutes=3, seconds=10)), "in 3m")
        self.assertEqual(describe_delta(timedelta(hours=2, minutes=15)), "in 2h 15m")
        self.assertEqual(describe_delta(timedelta(days=1, hours=3)), "in 1d 3h")
        self.assertEqual(describe_delta(timedelta(minutes=-5)), "5m ago")


if __name__ == "__main__":
    unittest.main()

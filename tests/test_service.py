"""Behavioural tests for AlarmService with a frozen clock."""

from __future__ import annotations

import unittest
from datetime import datetime, time, timedelta

from alarm_clock.errors import AlarmNotFound, AlarmNotRinging, InvalidDays, InvalidTime
from alarm_clock.models import EVERY_DAY, WEEKDAYS, WEEKENDS, AlarmState
from alarm_clock.repository import InMemoryAlarmRepository
from alarm_clock.service import AlarmService
from alarm_clock.timefmt import format_days, format_next, parse_days, parse_time


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)

    def set(self, value: datetime) -> None:
        self.now = value


SEVEN_AM = time(7, 0)
MONDAY = datetime(2026, 10, 5, 6, 0)  # 2026-10-05 is a Monday


class AlarmServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock(datetime(2026, 10, 6, 6, 0))  # Tuesday 06:00
        self.service = AlarmService(InMemoryAlarmRepository(), clock=self.clock)

    def state(self, alarm_id: int) -> AlarmState:
        return self.service.get(alarm_id).state(self.clock.now)

    # ---- create / list / delete ---------------------------------------

    def test_create_assigns_incrementing_ids(self) -> None:
        first = self.service.create(SEVEN_AM, "Gym")
        second = self.service.create(time(8, 0), "Standup")
        self.assertEqual([first.id, second.id], [1, 2])
        self.assertEqual([a.label for a in self.service.list_alarms()], ["Gym", "Standup"])

    def test_ids_are_not_reused_after_delete(self) -> None:
        self.service.create(SEVEN_AM)
        second = self.service.create(time(8, 0))
        self.service.delete(second.id)
        third = self.service.create(time(9, 0))
        self.assertEqual(third.id, 2)  # max surviving id + 1

    def test_delete_unknown_id_raises(self) -> None:
        with self.assertRaises(AlarmNotFound):
            self.service.delete(42)

    # ---- ringing ---------------------------------------------------------

    def test_alarm_rings_at_its_time_and_keeps_ringing_until_dismissed(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        self.assertEqual(self.state(alarm.id), AlarmState.SCHEDULED)

        self.clock.set(datetime(2026, 10, 6, 7, 0))
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

        self.clock.advance(minutes=20)
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

        self.service.dismiss(alarm.id)
        self.assertEqual(self.state(alarm.id), AlarmState.SCHEDULED)

    def test_alarm_created_after_its_time_waits_for_tomorrow(self) -> None:
        self.clock.set(datetime(2026, 10, 6, 9, 0))
        alarm = self.service.create(SEVEN_AM)
        self.assertEqual(self.state(alarm.id), AlarmState.SCHEDULED)

        self.clock.set(datetime(2026, 10, 7, 7, 0))
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

    def test_dismissed_alarm_rings_again_next_day(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        self.clock.set(datetime(2026, 10, 6, 7, 0))
        self.service.dismiss(alarm.id)
        self.clock.set(datetime(2026, 10, 7, 7, 0))
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

    # ---- snooze ----------------------------------------------------------

    def test_snooze_silences_then_rings_again(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        self.clock.set(datetime(2026, 10, 6, 7, 0))

        self.service.snooze(alarm.id, timedelta(minutes=5))
        self.assertEqual(self.state(alarm.id), AlarmState.SNOOZED)

        self.clock.advance(minutes=4)
        self.assertEqual(self.state(alarm.id), AlarmState.SNOOZED)

        self.clock.advance(minutes=1)
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

    def test_snooze_can_be_repeated(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        self.clock.set(datetime(2026, 10, 6, 7, 0))
        self.service.snooze(alarm.id, timedelta(minutes=5))
        self.clock.advance(minutes=5)
        self.service.snooze(alarm.id, timedelta(minutes=5))
        self.assertEqual(self.state(alarm.id), AlarmState.SNOOZED)
        self.clock.advance(minutes=5)
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

    def test_only_a_ringing_alarm_can_be_snoozed(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        with self.assertRaises(AlarmNotRinging):
            self.service.snooze(alarm.id)

    def test_snooze_across_midnight_does_not_skip_next_day(self) -> None:
        self.clock.set(datetime(2026, 10, 6, 23, 0))
        alarm = self.service.create(time(23, 55))
        self.clock.set(datetime(2026, 10, 6, 23, 55))
        self.service.snooze(alarm.id, timedelta(minutes=10))
        self.clock.set(datetime(2026, 10, 7, 0, 6))
        self.service.dismiss(alarm.id)
        self.clock.set(datetime(2026, 10, 7, 23, 55))
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

    # ---- activate / deactivate ------------------------------------------

    def test_deactivated_alarm_never_rings(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        self.service.deactivate(alarm.id)
        self.clock.set(datetime(2026, 10, 6, 7, 0))
        self.assertEqual(self.state(alarm.id), AlarmState.INACTIVE)
        self.assertEqual(self.service.ringing(), [])

    def test_deactivate_clears_snooze(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        self.clock.set(datetime(2026, 10, 6, 7, 0))
        self.service.snooze(alarm.id)
        self.service.deactivate(alarm.id)
        self.assertIsNone(self.service.get(alarm.id).snoozed_until)

    def test_reactivating_after_its_time_does_not_ring_immediately(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        self.service.deactivate(alarm.id)
        self.clock.set(datetime(2026, 10, 6, 9, 0))
        self.service.activate(alarm.id)
        self.assertEqual(self.state(alarm.id), AlarmState.SCHEDULED)
        self.clock.set(datetime(2026, 10, 7, 7, 0))
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

    def test_ringing_lists_only_ringing_alarms(self) -> None:
        early = self.service.create(SEVEN_AM)
        self.service.create(time(8, 0))
        self.clock.set(datetime(2026, 10, 6, 7, 30))
        self.assertEqual([a.id for a in self.service.ringing()], [early.id])

    # ---- repeat days and once --------------------------------------------

    def test_weekday_alarm_skips_the_weekend(self) -> None:
        self.clock.set(datetime(2026, 10, 9, 6, 0))  # Friday
        alarm = self.service.create(SEVEN_AM, days=WEEKDAYS)
        self.clock.set(datetime(2026, 10, 9, 7, 0))
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)
        self.service.dismiss(alarm.id)
        self.clock.set(datetime(2026, 10, 10, 7, 0))  # Saturday
        self.assertEqual(self.state(alarm.id), AlarmState.SCHEDULED)
        self.clock.set(datetime(2026, 10, 11, 7, 0))  # Sunday
        self.assertEqual(self.state(alarm.id), AlarmState.SCHEDULED)
        self.clock.set(datetime(2026, 10, 12, 7, 0))  # Monday
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

    def test_weekend_alarm_created_on_weekday_waits_for_saturday(self) -> None:
        alarm = self.service.create(SEVEN_AM, days=WEEKENDS)
        self.clock.set(datetime(2026, 10, 6, 7, 0))  # Tuesday
        self.assertEqual(self.state(alarm.id), AlarmState.SCHEDULED)
        self.assertEqual(
            self.service.get(alarm.id).next_ring_at(self.clock.now), datetime(2026, 10, 10, 7, 0)
        )

    def test_once_alarm_switches_off_after_dismissal(self) -> None:
        alarm = self.service.create(SEVEN_AM, once=True)
        self.clock.set(datetime(2026, 10, 6, 7, 0))
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)
        self.service.dismiss(alarm.id)
        self.assertEqual(self.state(alarm.id), AlarmState.INACTIVE)

    def test_once_alarm_survives_snooze(self) -> None:
        alarm = self.service.create(SEVEN_AM, once=True)
        self.clock.set(datetime(2026, 10, 6, 7, 0))
        self.service.snooze(alarm.id, timedelta(minutes=5))
        self.assertEqual(self.state(alarm.id), AlarmState.SNOOZED)
        self.clock.advance(minutes=5)
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

    # ---- next ring ------------------------------------------------------

    def test_next_ring_at(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        self.assertEqual(alarm.next_ring_at(self.clock.now), datetime(2026, 10, 6, 7, 0))
        self.clock.set(datetime(2026, 10, 6, 7, 30))
        self.service.dismiss(alarm.id)
        alarm = self.service.get(alarm.id)
        self.assertEqual(alarm.next_ring_at(self.clock.now), datetime(2026, 10, 7, 7, 0))
        self.service.deactivate(alarm.id)
        self.assertIsNone(self.service.get(alarm.id).next_ring_at(self.clock.now))

    # ---- update -----------------------------------------------------------

    def test_update_label_keeps_schedule(self) -> None:
        alarm = self.service.create(SEVEN_AM, "Gym")
        self.clock.set(datetime(2026, 10, 6, 7, 0))
        self.service.update(alarm.id, label="Run")
        updated = self.service.get(alarm.id)
        self.assertEqual(updated.label, "Run")
        self.assertEqual(updated.state(self.clock.now), AlarmState.RINGING)

    def test_update_time_resets_schedule_without_ringing_retroactively(self) -> None:
        alarm = self.service.create(time(9, 0))
        self.clock.set(datetime(2026, 10, 6, 8, 0))
        self.service.update(alarm.id, ring_at=SEVEN_AM)  # 07:00 already passed today
        self.assertEqual(self.state(alarm.id), AlarmState.SCHEDULED)
        self.clock.set(datetime(2026, 10, 7, 7, 0))
        self.assertEqual(self.state(alarm.id), AlarmState.RINGING)

    def test_update_days_and_once(self) -> None:
        alarm = self.service.create(SEVEN_AM)
        updated = self.service.update(alarm.id, days=WEEKDAYS, once=True)
        self.assertEqual(updated.days, WEEKDAYS)
        self.assertTrue(updated.once)

    def test_update_unknown_id_raises(self) -> None:
        with self.assertRaises(AlarmNotFound):
            self.service.update(9, label="x")


class ParseTimeTests(unittest.TestCase):
    def test_accepts_common_spellings(self) -> None:
        cases = {
            "07:30": time(7, 30),
            "7:30": time(7, 30),
            "19:05": time(19, 5),
            "7:30pm": time(19, 30),
            "7:30 AM": time(7, 30),
            "7am": time(7, 0),
            " 12:00 ": time(12, 0),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_time(raw), expected)

    def test_rejects_nonsense(self) -> None:
        for raw in ("", "25:00", "7:60", "noon", "0730"):
            with self.subTest(raw=raw), self.assertRaises(InvalidTime):
                parse_time(raw)


class ParseDaysTests(unittest.TestCase):
    def test_aliases_and_lists(self) -> None:
        cases = {
            "daily": EVERY_DAY,
            "Weekdays": WEEKDAYS,
            "weekends": WEEKENDS,
            "mon,wed,fri": frozenset({0, 2, 4}),
            "Monday, Sunday": frozenset({0, 6}),
            "sat": frozenset({5}),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_days(raw), expected)

    def test_rejects_nonsense(self) -> None:
        for raw in ("", "mo", "funday", "mon,,tue", "1,2"):
            with self.subTest(raw=raw), self.assertRaises(InvalidDays):
                parse_days(raw)

    def test_format_days_round_trips(self) -> None:
        for raw in ("daily", "weekdays", "weekends", "Mon,Wed,Fri"):
            with self.subTest(raw=raw):
                self.assertEqual(format_days(parse_days(raw)), raw.lower() if "," not in raw else raw)


class FormatNextTests(unittest.TestCase):
    def test_wording(self) -> None:
        now = datetime(2026, 10, 6, 6, 0)
        self.assertEqual(format_next(datetime(2026, 10, 6, 7, 0), now), "07:00 today")
        self.assertEqual(format_next(datetime(2026, 10, 7, 7, 0), now), "07:00 tomorrow")
        self.assertEqual(format_next(datetime(2026, 10, 10, 7, 0), now), "Sat 07:00")


if __name__ == "__main__":
    unittest.main()

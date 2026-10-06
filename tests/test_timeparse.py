import unittest
from datetime import time, timedelta

from alarmclock.timeparse import (
    TimeParseError,
    is_relative,
    parse_relative,
    parse_repeat,
    parse_time_of_day,
)


class TimeOfDayTests(unittest.TestCase):
    def test_24h_forms(self):
        self.assertEqual(parse_time_of_day("07:30"), time(7, 30))
        self.assertEqual(parse_time_of_day("7:30"), time(7, 30))
        self.assertEqual(parse_time_of_day("00:00"), time(0, 0))
        self.assertEqual(parse_time_of_day("23:59"), time(23, 59))

    def test_12h_forms(self):
        self.assertEqual(parse_time_of_day("7am"), time(7, 0))
        self.assertEqual(parse_time_of_day("7:30pm"), time(19, 30))
        self.assertEqual(parse_time_of_day("7:30 PM"), time(19, 30))
        self.assertEqual(parse_time_of_day("12am"), time(0, 0))
        self.assertEqual(parse_time_of_day("12pm"), time(12, 0))
        self.assertEqual(parse_time_of_day("12:30am"), time(0, 30))

    def test_bare_hour_is_ambiguous(self):
        with self.assertRaises(TimeParseError):
            parse_time_of_day("7")

    def test_out_of_range(self):
        for bad in ("24:00", "7:60", "13pm", "0am", "abc", "", "7:3"):
            with self.subTest(bad=bad), self.assertRaises(TimeParseError):
                parse_time_of_day(bad)


class RelativeTests(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse_relative("+10m"), timedelta(minutes=10))
        self.assertEqual(parse_relative("+90"), timedelta(minutes=90))
        self.assertEqual(parse_relative("+1h"), timedelta(hours=1))
        self.assertEqual(parse_relative("+1h30m"), timedelta(hours=1, minutes=30))
        self.assertEqual(parse_relative("+1h 30"), timedelta(hours=1, minutes=30))

    def test_rejects(self):
        for bad in ("+0m", "+24h", "+", "10m", "+1d"):
            with self.subTest(bad=bad), self.assertRaises(TimeParseError):
                parse_relative(bad)

    def test_is_relative(self):
        self.assertTrue(is_relative("+5m"))
        self.assertFalse(is_relative("5pm"))


class RepeatTests(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(parse_repeat(None), [])
        self.assertEqual(parse_repeat("once"), [])
        self.assertEqual(parse_repeat("daily"), [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(parse_repeat("weekdays"), [0, 1, 2, 3, 4])
        self.assertEqual(parse_repeat("WEEKENDS"), [5, 6])

    def test_day_lists(self):
        self.assertEqual(parse_repeat("mon,wed,fri"), [0, 2, 4])
        self.assertEqual(parse_repeat("Sunday, Monday"), [0, 6])

    def test_rejects(self):
        with self.assertRaises(TimeParseError):
            parse_repeat("mon,funday")


if __name__ == "__main__":
    unittest.main()

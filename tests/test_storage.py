import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from alarmclock.models import Alarm, AlarmNotFound, AmbiguousAlarmId, find_alarm
from alarmclock.storage import AlarmStore, StoreError


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AlarmStore(Path(self.tmp.name) / "nested" / "alarms.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_empty(self):
        self.assertEqual(self.store.load(), [])

    def test_round_trip(self):
        alarm = Alarm(id="ab12", hour=7, minute=30, label="Stand-up", days=[0, 2],
                      next_fire=datetime(2026, 10, 7, 7, 30), snooze_minutes=9)
        self.store.save([alarm])
        loaded = self.store.load()
        self.assertEqual(loaded, [alarm])
        self.assertFalse(list(self.store.path.parent.glob(".alarms-*")), "temp file left behind")

    def test_update_mutates_only_target(self):
        a = Alarm(id="a", hour=7, minute=0)
        b = Alarm(id="b", hour=8, minute=0)
        self.store.save([a, b])

        def mutate(alarm):
            alarm.enabled = False

        self.store.update("b", mutate)
        loaded = {x.id: x for x in self.store.load()}
        self.assertTrue(loaded["a"].enabled)
        self.assertFalse(loaded["b"].enabled)

    def test_update_missing_raises(self):
        with self.assertRaises(AlarmNotFound):
            self.store.update("zzz", lambda a: None)

    def test_corrupt_file(self):
        self.store.path.parent.mkdir(parents=True)
        self.store.path.write_text("{not json")
        with self.assertRaises(StoreError):
            self.store.load()


class FindAlarmTests(unittest.TestCase):
    alarms = [Alarm(id="ab12", hour=7, minute=0), Alarm(id="ab99", hour=8, minute=0),
              Alarm(id="cd00", hour=9, minute=0)]

    def test_exact_and_prefix(self):
        self.assertIs(find_alarm(self.alarms, "ab12"), self.alarms[0])
        self.assertIs(find_alarm(self.alarms, "c"), self.alarms[2])

    def test_ambiguous_and_missing(self):
        with self.assertRaises(AmbiguousAlarmId):
            find_alarm(self.alarms, "ab")
        with self.assertRaises(AlarmNotFound):
            find_alarm(self.alarms, "zz")


if __name__ == "__main__":
    unittest.main()

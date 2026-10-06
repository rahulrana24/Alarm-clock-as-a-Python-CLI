"""Round-trip tests for the JSON store."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, time
from pathlib import Path

from alarm_clock.models import Alarm
from alarm_clock.repository import JsonAlarmRepository


class JsonAlarmRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "nested" / "alarms.json"
        self.repo = JsonAlarmRepository(self.path)

    def test_missing_file_means_no_alarms(self) -> None:
        self.assertEqual(self.repo.load(), [])

    def test_round_trip_preserves_every_field(self) -> None:
        alarm = Alarm(
            id=7,
            label="Gym",
            ring_at=time(7, 30),
            is_active=False,
            snoozed_until=datetime(2026, 10, 6, 7, 35),
            dismissed_on=date(2026, 10, 5),
            created_at=datetime(2026, 10, 1, 12, 0, 0),
        )
        self.repo.save([alarm])
        self.assertEqual(self.repo.load(), [alarm])

    def test_save_creates_parent_directories_and_no_temp_file_remains(self) -> None:
        self.repo.save([Alarm(id=1, label="", ring_at=time(6, 0))])
        self.assertTrue(self.path.exists())
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["alarms.json"])


if __name__ == "__main__":
    unittest.main()

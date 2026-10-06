import contextlib
import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from alarmclock import cli
from alarmclock.storage import AlarmStore

NOW = datetime(2026, 10, 6, 9, 15, 0)  # Tuesday


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "alarms.json")
        self.store = AlarmStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "_now", return_value=NOW):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["--store", self.path, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_add_and_list(self):
        code, out, _ = self.run_cli("add", "7:30pm", "-l", "Gym", "-r", "weekdays")
        self.assertEqual(code, 0)
        self.assertIn("19:30 weekdays \"Gym\"", out)
        self.assertIn("Tue 06 Oct 19:30", out)

        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("Gym", out)
        self.assertIn("in 10h 15m", out)
        self.assertIn("on", out)

    def test_relative_add(self):
        code, out, _ = self.run_cli("add", "+45m", "-l", "Tea")
        self.assertEqual(code, 0)
        alarm = self.store.load()[0]
        self.assertEqual(alarm.next_fire, datetime(2026, 10, 6, 10, 0))
        self.assertEqual((alarm.hour, alarm.minute), (10, 0))
        self.assertFalse(alarm.is_repeating)

    def test_relative_cannot_repeat(self):
        code, _, err = self.run_cli("add", "+10m", "-r", "daily")
        self.assertEqual(code, 1)
        self.assertIn("cannot repeat", err)

    def test_bad_time_is_user_error(self):
        code, _, err = self.run_cli("add", "25:00")
        self.assertEqual(code, 1)
        self.assertIn("error:", err)

    def test_remove_disable_enable_by_prefix(self):
        self.run_cli("add", "08:00", "-l", "A")
        alarm_id = self.store.load()[0].id

        code, out, _ = self.run_cli("disable", alarm_id[:2])
        self.assertEqual(code, 0)
        self.assertFalse(self.store.load()[0].enabled)
        _, out, _ = self.run_cli("list")
        self.assertIn("off", out)

        code, out, _ = self.run_cli("enable", alarm_id)
        self.assertEqual(code, 0)
        self.assertEqual(self.store.load()[0].next_fire, datetime(2026, 10, 7, 8, 0))

        code, out, _ = self.run_cli("rm", alarm_id)
        self.assertEqual(code, 0)
        self.assertEqual(self.store.load(), [])

        code, _, err = self.run_cli("remove", "nope")
        self.assertEqual(code, 1)
        self.assertIn("no alarm", err)

    def test_empty_list(self):
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("No alarms", out)


if __name__ == "__main__":
    unittest.main()

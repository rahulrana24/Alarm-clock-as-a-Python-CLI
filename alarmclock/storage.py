"""JSON persistence. One file, written atomically, re-read on every access."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from .models import Alarm, AlarmNotFound

FORMAT_VERSION = 1


class StoreError(RuntimeError):
    pass


class AlarmStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    @staticmethod
    def default_path() -> Path:
        home = os.environ.get("ALARMCLOCK_HOME")
        base = Path(home) if home else Path.home() / ".alarmclock"
        return base / "alarms.json"

    def load(self) -> list[Alarm]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("version") != FORMAT_VERSION:
                raise StoreError(f"unsupported store version in {self.path}")
            return [Alarm.from_dict(item) for item in data.get("alarms", [])]
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            raise StoreError(f"cannot read {self.path}: {exc}") from exc

    def save(self, alarms: list[Alarm]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": FORMAT_VERSION, "alarms": [a.to_dict() for a in alarms]}
        # Write to a sibling temp file, then rename: readers never see a torn file.
        fd, tmp_name = tempfile.mkstemp(prefix=".alarms-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
                fh.write("\n")
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def update(self, alarm_id: str, mutate: Callable[[Alarm], None]) -> Alarm:
        """Read-modify-write a single alarm by exact id. Used by the runner so a
        change made elsewhere during a long ring is not overwritten."""
        alarms = self.load()
        for alarm in alarms:
            if alarm.id == alarm_id:
                mutate(alarm)
                self.save(alarms)
                return alarm
        raise AlarmNotFound(f"alarm {alarm_id} no longer exists")

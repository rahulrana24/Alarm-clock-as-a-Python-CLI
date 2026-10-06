"""Persistence for alarms.

``AlarmRepository`` is the only contract the service depends on. To store
alarms somewhere else (SQLite, a REST API, ...) implement ``load`` and
``save`` on a new class and hand it to ``AlarmService``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

from alarm_clock.models import Alarm

DEFAULT_STORE = Path.home() / ".alarm_clock" / "alarms.json"
STORE_ENV_VAR = "ALARM_CLOCK_STORE"


class AlarmRepository(Protocol):
    def load(self) -> list[Alarm]: ...

    def save(self, alarms: list[Alarm]) -> None: ...


class InMemoryAlarmRepository:
    """Keeps alarms in a list. Used by tests and handy for scripting."""

    def __init__(self, alarms: list[Alarm] | None = None) -> None:
        self._alarms = list(alarms or [])

    def load(self) -> list[Alarm]:
        return list(self._alarms)

    def save(self, alarms: list[Alarm]) -> None:
        self._alarms = list(alarms)


class JsonAlarmRepository:
    """Stores alarms as a JSON document on disk.

    Writes go to a temporary file first and are then renamed into place, so a
    crash mid-write never leaves a half-written store behind.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Alarm]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            document = json.load(fh)
        return [Alarm.from_dict(item) for item in document.get("alarms", [])]

    def save(self, alarms: list[Alarm]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {"alarms": [alarm.to_dict() for alarm in alarms]}
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(document, fh, indent=2)
        os.replace(tmp_path, self.path)


def resolve_store_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Pick the store file: CLI flag, then env var, then the default."""
    if explicit:
        return Path(explicit).expanduser()
    if env_value := os.environ.get(STORE_ENV_VAR):
        return Path(env_value).expanduser()
    return DEFAULT_STORE

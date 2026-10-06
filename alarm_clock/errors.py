"""Domain errors raised by the alarm clock.

The CLI catches ``AlarmError`` and turns it into a friendly message and a
non-zero exit code, so every error raised on purpose should subclass it.
"""


class AlarmError(Exception):
    """Base class for all alarm-clock domain errors."""


class AlarmNotFound(AlarmError):
    def __init__(self, alarm_id: int) -> None:
        super().__init__(f"No alarm with id {alarm_id}.")
        self.alarm_id = alarm_id


class AlarmNotRinging(AlarmError):
    def __init__(self, alarm_id: int) -> None:
        super().__init__(f"Alarm {alarm_id} is not ringing, so it cannot be snoozed.")
        self.alarm_id = alarm_id


class InvalidTime(AlarmError):
    def __init__(self, raw: str) -> None:
        super().__init__(
            f"Could not understand time {raw!r}. Use HH:MM (24h) or H:MMam/pm, e.g. 07:30 or 7:30pm."
        )
        self.raw = raw


class InvalidDays(AlarmError):
    def __init__(self, raw: str) -> None:
        super().__init__(
            f"Could not understand days {raw!r}. "
            "Use daily, weekdays, weekends, or a list like mon,wed,fri."
        )
        self.raw = raw


class WatcherAlreadyRunning(AlarmError):
    def __init__(self, pid: int) -> None:
        super().__init__(f"The alarm watcher is already running (pid {pid}).")
        self.pid = pid


class WatcherNotRunning(AlarmError):
    def __init__(self) -> None:
        super().__init__("The alarm watcher is not running.")

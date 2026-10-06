"""Run the watcher as a background process.

A pid file and a log file live next to the alarm store, so each store has
its own watcher. ``start`` spawns a detached process, ``stop`` sends it
SIGTERM, and ``pid`` reports whether it is still alive, cleaning up a stale
pid file left by a crash or a reboot.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from alarm_clock.errors import WatcherAlreadyRunning, WatcherNotRunning

STOP_TIMEOUT = 3.0  # seconds to wait for the watcher to exit after SIGTERM


@dataclass(frozen=True, slots=True)
class WatcherDaemon:
    pid_file: Path
    log_file: Path

    @classmethod
    def beside(cls, store: Path) -> WatcherDaemon:
        return cls(pid_file=store.parent / "watch.pid", log_file=store.parent / "watch.log")

    def pid(self) -> int | None:
        """The running watcher's pid, or None. Removes a stale pid file."""
        try:
            pid = int(self.pid_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None
        if _alive(pid):
            return pid
        self.pid_file.unlink(missing_ok=True)
        return None

    def start(self, command: list[str]) -> int:
        running = self.pid()
        if running is not None:
            raise WatcherAlreadyRunning(running)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # survives the terminal closing
            )
        self.pid_file.write_text(str(process.pid), encoding="utf-8")
        return process.pid

    def stop(self) -> int:
        pid = self.pid()
        if pid is None:
            raise WatcherNotRunning()
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + STOP_TIMEOUT
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)
        self.pid_file.unlink(missing_ok=True)
        return pid


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True

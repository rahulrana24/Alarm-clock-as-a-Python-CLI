"""Ways the user can react to a ringing alarm while the watcher runs.

A ``ReactionSource`` is told whenever the set of ringing alarms changes and
is polled frequently for a ``Reaction``. Two sources ship by default:

* ``KeyboardSource``: single key presses in the terminal (s, d, q).
* ``DialogSource``: a macOS dialog with Snooze / Dismiss buttons, which also
  works when the watcher runs in the background with no terminal.
"""

from __future__ import annotations

import os
import queue
import select
import shutil
import subprocess
import sys
import threading
from enum import Enum
from typing import Protocol, TextIO

from alarm_clock.models import Alarm
from alarm_clock.notify import applescript_string
from alarm_clock.timefmt import format_time

try:  # POSIX only; on other platforms the keyboard source simply disables itself
    import termios
    import tty
except ImportError:  # pragma: no cover
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]


class Reaction(Enum):
    SNOOZE = "snooze"
    DISMISS = "dismiss"
    QUIT = "quit"


class ReactionSource(Protocol):
    hint: str | None  # one line telling the user how to use this source

    def ringing_changed(self, alarms: list[Alarm]) -> None: ...

    def poll(self) -> Reaction | None: ...

    def close(self) -> None: ...


class KeyboardSource:
    """Reads single key presses without waiting for Enter.

    Enabled only when ``stream`` is an interactive terminal; otherwise every
    poll returns None, so the watcher can run with stdin closed.
    """

    KEYS = {"s": Reaction.SNOOZE, "d": Reaction.DISMISS, "q": Reaction.QUIT}

    def __init__(self, stream: TextIO = sys.stdin) -> None:
        self._fd: int | None = None
        self._saved_attrs = None
        if termios is None or not _is_tty(stream):
            return
        self._fd = stream.fileno()
        self._saved_attrs = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)

    @property
    def enabled(self) -> bool:
        return self._fd is not None

    @property
    def hint(self) -> str | None:
        if not self.enabled:
            return None
        return "Keys: [s] snooze   [d] dismiss   [q] quit"

    def ringing_changed(self, alarms: list[Alarm]) -> None:
        pass

    def poll(self) -> Reaction | None:
        if self._fd is None:
            return None
        while select.select([self._fd], [], [], 0)[0]:
            key = os.read(self._fd, 1).decode(errors="ignore").lower()
            if key in self.KEYS:
                return self.KEYS[key]
        return None

    def close(self) -> None:
        if self._fd is not None and self._saved_attrs is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved_attrs)
            self._fd = None


class DialogSource:
    """A macOS dialog with Snooze and Dismiss buttons.

    The dialog is opened in a subprocess whenever alarms start ringing and
    closed again when they stop (for example after a dismissal from another
    terminal). The button pressed is handed back through ``poll``.
    """

    hint = "A Snooze / Dismiss dialog pops up while an alarm rings."

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._results: queue.Queue[Reaction] = queue.Queue()

    @staticmethod
    def available() -> bool:
        return sys.platform == "darwin" and shutil.which("osascript") is not None

    def ringing_changed(self, alarms: list[Alarm]) -> None:
        self._cancel()
        if alarms:
            self._open(alarms)

    def poll(self) -> Reaction | None:
        try:
            return self._results.get_nowait()
        except queue.Empty:
            return None

    def close(self) -> None:
        self._cancel()

    def _open(self, alarms: list[Alarm]) -> None:
        lines = [f"{alarm.label or 'Alarm'}  ({format_time(alarm.ring_at)})" for alarm in alarms]
        script = (
            f"display dialog {applescript_string(chr(10).join(lines))} "
            'with title "Alarm" buttons {"Snooze", "Dismiss"} '
            'default button "Dismiss" with icon caution'
        )
        self._process = subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        threading.Thread(target=self._collect, args=(self._process,), daemon=True).start()

    def _collect(self, process: subprocess.Popen[str]) -> None:
        output, _ = process.communicate()
        if process.returncode != 0:  # cancelled by us, or closed with Escape
            return
        if "Snooze" in output:
            self._results.put(Reaction.SNOOZE)
        elif "Dismiss" in output:
            self._results.put(Reaction.DISMISS)

    def _cancel(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
        self._process = None


def _is_tty(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False

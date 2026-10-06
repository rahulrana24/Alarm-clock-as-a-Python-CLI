"""Making noise. The runner only knows about `beep()`."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol, TextIO


class Ringer(Protocol):
    def beep(self) -> None: ...


class SilentRinger:
    def beep(self) -> None:
        pass


class TerminalBell:
    """ASCII BEL. Works in any terminal that has not muted it."""

    def __init__(self, out: TextIO = sys.stdout):
        self.out = out

    def beep(self) -> None:
        self.out.write("\a")
        self.out.flush()


class MacSoundRinger(TerminalBell):
    """BEL plus a macOS system sound via `afplay`, non-blocking, best effort.
    Only one afplay runs at a time so a one-second tick never piles up players."""

    SOUND = Path("/System/Library/Sounds/Glass.aiff")

    def __init__(self, out: TextIO = sys.stdout):
        super().__init__(out)
        self._proc: subprocess.Popen | None = None

    def beep(self) -> None:
        super().beep()
        if self._proc is not None and self._proc.poll() is None:
            return
        try:
            self._proc = subprocess.Popen(
                ["afplay", str(self.SOUND)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self._proc = None


def default_ringer(silent: bool = False, out: TextIO = sys.stdout) -> Ringer:
    if silent:
        return SilentRinger()
    if sys.platform == "darwin" and shutil.which("afplay") and MacSoundRinger.SOUND.exists():
        return MacSoundRinger(out)
    return TerminalBell(out)

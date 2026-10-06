"""OS-level alerts: desktop notifications and sound.

A ``Notifier`` only talks to the operating system. What is said, and when, is
decided by the watcher. ``make_notifier`` picks the best implementation for
the current machine and falls back to the terminal bell.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol, TextIO

MAC_DEFAULT_SOUND = Path("/System/Library/Sounds/Glass.aiff")
LINUX_DEFAULT_SOUND = Path("/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga")


class Notifier(Protocol):
    def notify(self, title: str, message: str) -> None:
        """Show a one-off alert to the user."""

    def chime(self) -> None:
        """Make a short noise. Called repeatedly while something rings."""

    def close(self) -> None:
        """Stop any noise still playing and release resources."""


class TerminalNotifier:
    """Fallback for any platform: rings the terminal bell."""

    def __init__(self, bell: bool = True, out: TextIO = sys.stdout) -> None:
        self._bell = bell
        self._out = out

    def notify(self, title: str, message: str) -> None:
        self.chime()

    def chime(self) -> None:
        if self._bell:
            self._out.write("\a")
            self._out.flush()

    def close(self) -> None:
        pass


class _SoundPlayer:
    """Plays a sound file through an external command, never overlapping
    itself, so repeated chimes do not pile up."""

    def __init__(self, command: list[str] | None) -> None:
        self._command = command
        self._process: subprocess.Popen[bytes] | None = None

    def play(self) -> None:
        if self._command is None or self._is_playing():
            return
        self._process = subprocess.Popen(
            self._command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def stop(self) -> None:
        if self._is_playing():
            assert self._process is not None
            self._process.terminate()

    def _is_playing(self) -> bool:
        return self._process is not None and self._process.poll() is None


class MacNotifier:
    """Notification Center banner via osascript, sound via afplay."""

    def __init__(self, sound: Path | None) -> None:
        self._player = _SoundPlayer(["afplay", str(sound)] if sound else None)

    def notify(self, title: str, message: str) -> None:
        script = (
            f"display notification {applescript_string(message)} "
            f"with title {applescript_string(title)}"
        )
        subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        self.chime()

    def chime(self) -> None:
        self._player.play()

    def close(self) -> None:
        self._player.stop()


class LinuxNotifier:
    """Desktop banner via notify-send, sound via whichever player exists."""

    PLAYERS = (["paplay"], ["aplay", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"])

    def __init__(self, sound: Path | None) -> None:
        self._player = _SoundPlayer(self._player_command(sound))

    @classmethod
    def _player_command(cls, sound: Path | None) -> list[str] | None:
        if sound is None:
            return None
        for command in cls.PLAYERS:
            if shutil.which(command[0]):
                return [*command, str(sound)]
        return None

    def notify(self, title: str, message: str) -> None:
        subprocess.run(["notify-send", "--urgency=critical", title, message], check=False)
        self.chime()

    def chime(self) -> None:
        self._player.play()

    def close(self) -> None:
        self._player.stop()


def applescript_string(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def make_notifier(silent: bool = False, sound: Path | None = None) -> Notifier:
    """Choose a notifier for this machine.

    ``silent`` disables sound entirely. ``sound`` overrides the platform's
    default sound file.
    """
    if sys.platform == "darwin" and shutil.which("osascript"):
        return MacNotifier(sound=None if silent else sound or MAC_DEFAULT_SOUND)
    if shutil.which("notify-send"):
        return LinuxNotifier(sound=None if silent else sound or LINUX_DEFAULT_SOUND)
    return TerminalNotifier(bell=not silent)

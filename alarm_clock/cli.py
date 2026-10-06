"""Command-line interface.

Each sub-command is a small ``Command`` object: a name, a function that adds
its arguments to argparse, and a function that runs it against the app.
To add a command, write those two functions and append to ``COMMANDS``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path

from alarm_clock import __version__
from alarm_clock.daemon import WatcherDaemon
from alarm_clock.errors import AlarmError
from alarm_clock.inputs import DialogSource, KeyboardSource, ReactionSource
from alarm_clock.models import Alarm, AlarmState
from alarm_clock.notify import make_notifier
from alarm_clock.repository import JsonAlarmRepository, resolve_store_path
from alarm_clock.service import DEFAULT_SNOOZE, AlarmService
from alarm_clock.timefmt import (
    format_datetime,
    format_days,
    format_next,
    format_time,
    parse_days,
    parse_time,
)
from alarm_clock.watcher import Watcher

EXIT_OK = 0
EXIT_ERROR = 1

DEFAULT_WATCH_INTERVAL = 5
DEFAULT_SNOOZE_MINUTES = int(DEFAULT_SNOOZE.total_seconds() // 60)


@dataclass
class App:
    """Everything a command may need, built once per invocation."""

    store: Path

    @cached_property
    def service(self) -> AlarmService:
        return AlarmService(JsonAlarmRepository(self.store))

    @cached_property
    def daemon(self) -> WatcherDaemon:
        return WatcherDaemon.beside(self.store)


# ---- presentation --------------------------------------------------------


def describe(alarm: Alarm, now: datetime) -> str:
    state = alarm.state(now)
    repeat = "once" if alarm.once else format_days(alarm.days)
    label = alarm.label or "(no label)"
    detail = ""
    if state is AlarmState.SNOOZED and alarm.snoozed_until is not None:
        detail = f"until {format_datetime(alarm.snoozed_until)}"
    elif state is AlarmState.SCHEDULED and (next_ring := alarm.next_ring_at(now)):
        detail = f"next {format_next(next_ring, now)}"
    return f"[{alarm.id:>3}]  {format_time(alarm.ring_at)}  {repeat:<8}  {state.value:<9}  {label:<20}  {detail}".rstrip()


def print_alarms(alarms: Sequence[Alarm], now: datetime, empty_message: str) -> None:
    if not alarms:
        print(empty_message)
        return
    for alarm in alarms:
        print(describe(alarm, now))


# ---- shared argument groups -----------------------------------------------


def add_id_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("id", type=int, help="alarm id, see `alarm list`")


def add_watch_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-i", "--interval", type=positive_int, default=DEFAULT_WATCH_INTERVAL,
        help="seconds between checks (default: %(default)s)",
    )
    parser.add_argument(
        "--snooze", type=positive_int, default=DEFAULT_SNOOZE_MINUTES, metavar="MINUTES",
        help="snooze length when snoozing from the watcher (default: %(default)s)",
    )
    parser.add_argument("--silent", action="store_true", help="no sound, notifications only")
    parser.add_argument("--sound", metavar="FILE", help="sound file to play instead of the default")
    parser.add_argument("--no-dialog", action="store_true", help="do not pop up a Snooze/Dismiss dialog")


def watch_options_to_argv(args: argparse.Namespace) -> list[str]:
    """Inverse of ``add_watch_options``: used to relaunch ``watch`` in the background."""
    argv = ["--interval", str(args.interval), "--snooze", str(args.snooze)]
    if args.silent:
        argv.append("--silent")
    if args.sound:
        argv += ["--sound", args.sound]
    if args.no_dialog:
        argv.append("--no-dialog")
    return argv


# ---- commands --------------------------------------------------------------


def configure_add(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("time", help="when to ring, e.g. 07:30 or 7:30pm")
    parser.add_argument("-l", "--label", default="", help="what the alarm is for")
    parser.add_argument(
        "-d", "--days", default="daily",
        help="daily, weekdays, weekends, or a list like mon,wed,fri (default: %(default)s)",
    )
    parser.add_argument("--once", action="store_true", help="switch off after it rings once")


def run_add(app: App, args: argparse.Namespace) -> None:
    alarm = app.service.create(
        parse_time(args.time), label=args.label, days=parse_days(args.days), once=args.once
    )
    print(f"Created alarm {alarm.id}.")
    print(describe(alarm, app.service.now()))


def configure_edit(parser: argparse.ArgumentParser) -> None:
    add_id_argument(parser)
    parser.add_argument("-t", "--time", help="new ring time")
    parser.add_argument("-l", "--label", help="new label")
    parser.add_argument("-d", "--days", help="new repeat days")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", dest="once", action="store_true", default=None, help="ring once, then switch off")
    group.add_argument("--repeat", dest="once", action="store_false", help="keep ringing on its days")


def run_edit(app: App, args: argparse.Namespace) -> None:
    if args.time is None and args.label is None and args.days is None and args.once is None:
        raise AlarmError("Nothing to change. Pass --time, --label, --days, --once or --repeat.")
    alarm = app.service.update(
        args.id,
        ring_at=None if args.time is None else parse_time(args.time),
        label=args.label,
        days=None if args.days is None else parse_days(args.days),
        once=args.once,
    )
    print(describe(alarm, app.service.now()))


def configure_list(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--active", action="store_true", help="show only active alarms")


def run_list(app: App, args: argparse.Namespace) -> None:
    alarms = app.service.list_alarms()
    if args.active:
        alarms = [alarm for alarm in alarms if alarm.is_active]
    print_alarms(alarms, app.service.now(), "No alarms. Add one with: alarm add 07:30 --label Gym")


def run_delete(app: App, args: argparse.Namespace) -> None:
    alarm = app.service.delete(args.id)
    print(f"Deleted alarm {alarm.id} ({format_time(alarm.ring_at)} {alarm.label}).")


def run_activate(app: App, args: argparse.Namespace) -> None:
    print(describe(app.service.activate(args.id), app.service.now()))


def run_deactivate(app: App, args: argparse.Namespace) -> None:
    print(describe(app.service.deactivate(args.id), app.service.now()))


def configure_snooze(parser: argparse.ArgumentParser) -> None:
    add_id_argument(parser)
    parser.add_argument(
        "-m", "--minutes", type=positive_int, default=DEFAULT_SNOOZE_MINUTES,
        help="how long to snooze (default: %(default)s)",
    )


def run_snooze(app: App, args: argparse.Namespace) -> None:
    alarm = app.service.snooze(args.id, timedelta(minutes=args.minutes))
    print(describe(alarm, app.service.now()))


def run_dismiss(app: App, args: argparse.Namespace) -> None:
    print(describe(app.service.dismiss(args.id), app.service.now()))


def run_ring(app: App, args: argparse.Namespace) -> None:
    """Print alarms ringing right now. Exit code 0 either way, so it is safe
    to call from scripts."""
    ringing = app.service.ringing()
    print_alarms(ringing, app.service.now(), "Nothing is ringing.")


def run_watch(app: App, args: argparse.Namespace) -> None:
    """Stay in the foreground, ring alarms and take snooze/dismiss input."""
    sources: list[ReactionSource] = [KeyboardSource()]
    if DialogSource.available() and not args.no_dialog:
        sources.append(DialogSource())
    notifier = make_notifier(silent=args.silent, sound=Path(args.sound) if args.sound else None)
    Watcher(
        app.service,
        notifier,
        sources,
        interval=args.interval,
        snooze=timedelta(minutes=args.snooze),
    ).run()


def run_start(app: App, args: argparse.Namespace) -> None:
    """Launch ``watch`` as a background process."""
    command = [
        sys.executable, "-u", "-m", "alarm_clock", "--store", str(app.store),
        "watch", *watch_options_to_argv(args),
    ]
    pid = app.daemon.start(command)
    print(f"Alarm watcher started in the background (pid {pid}).")
    print(f"Log: {app.daemon.log_file}")


def run_stop(app: App, args: argparse.Namespace) -> None:
    pid = app.daemon.stop()
    print(f"Alarm watcher stopped (pid {pid}).")


def run_status(app: App, args: argparse.Namespace) -> None:
    pid = app.daemon.pid()
    if pid is None:
        print("Alarm watcher is not running. Start it with: alarm start")
    else:
        print(f"Alarm watcher is running (pid {pid}). Log: {app.daemon.log_file}")
    print(f"Store: {app.store}")
    print_alarms(app.service.ringing(), app.service.now(), "Nothing is ringing.")


# ---- registry --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    help: str
    run: Callable[[App, argparse.Namespace], None]
    configure: Callable[[argparse.ArgumentParser], None] = lambda parser: None


COMMANDS: tuple[Command, ...] = (
    Command("add", "create a new alarm", run_add, configure_add),
    Command("edit", "change an alarm's time, label or days", run_edit, configure_edit),
    Command("list", "show all alarms", run_list, configure_list),
    Command("delete", "delete an alarm by id", run_delete, add_id_argument),
    Command("activate", "switch an alarm on", run_activate, add_id_argument),
    Command("deactivate", "switch an alarm off", run_deactivate, add_id_argument),
    Command("snooze", "snooze a ringing alarm", run_snooze, configure_snooze),
    Command("dismiss", "stop a ringing alarm until its next occurrence", run_dismiss, add_id_argument),
    Command("ring", "show which alarms are ringing now", run_ring),
    Command("watch", "ring alarms in this terminal (sound, notification, keys)", run_watch, add_watch_options),
    Command("start", "run the watcher in the background", run_start, add_watch_options),
    Command("stop", "stop the background watcher", run_stop),
    Command("status", "is the background watcher running? what is ringing?", run_status),
)


def positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive whole number")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alarm", description="A command-line alarm clock.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--store", metavar="PATH",
        help="where alarms are saved (default: $ALARM_CLOCK_STORE or ~/.alarm_clock/alarms.json)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for command in COMMANDS:
        sub = subparsers.add_parser(command.name, help=command.help)
        command.configure(sub)
        sub.set_defaults(run=command.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = App(store=resolve_store_path(args.store))
    try:
        args.run(app, args)
    except AlarmError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

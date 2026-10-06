"""argparse surface. Thin: parse, call the right module, format output."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import datetime

from . import __version__
from .models import Alarm, AlarmNotFound, AmbiguousAlarmId, find_alarm, new_id
from .ringer import default_ringer
from .runner import Runner, RunnerConfig, StdinInput
from .scheduler import describe_delta, first_fire_for, next_occurrence
from .storage import AlarmStore, StoreError
from .timeparse import (
    TimeParseError,
    is_relative,
    parse_relative,
    parse_repeat,
    parse_time_of_day,
)

Clock = Callable[[], datetime]


def _now() -> datetime:
    """Single seam for the wall clock so tests can pin it."""
    return datetime.now()


# -- commands --------------------------------------------------------------


def cmd_add(args: argparse.Namespace, store: AlarmStore, clock: Clock | None = None) -> int:
    now = (clock or _now)()
    days = parse_repeat(args.repeat)
    if args.snooze <= 0:
        raise TimeParseError("--snooze must be at least 1 minute")

    if is_relative(args.when):
        if days:
            raise TimeParseError("a relative alarm (+10m) cannot repeat; give a time of day")
        fire = (now + parse_relative(args.when)).replace(microsecond=0)
        hour, minute = fire.hour, fire.minute
    else:
        at = parse_time_of_day(args.when)
        hour, minute = at.hour, at.minute
        fire = next_occurrence(at, days, now)

    alarms = store.load()
    taken = {a.id for a in alarms}
    alarm_id = new_id()
    while alarm_id in taken:
        alarm_id = new_id()

    alarm = Alarm(
        id=alarm_id,
        hour=hour,
        minute=minute,
        label=args.label or "",
        days=days,
        snooze_minutes=args.snooze,
        next_fire=fire,
    )
    alarms.append(alarm)
    store.save(alarms)
    print(f"Added {alarm.id}: {_describe(alarm)}; fires {fire:%a %d %b %H:%M} ({describe_delta(fire - now)})")
    return 0


def cmd_list(args: argparse.Namespace, store: AlarmStore, clock: Clock | None = None) -> int:
    now = (clock or _now)()
    alarms = sorted(store.load(), key=lambda a: (not a.enabled, a.next_fire or datetime.max))
    if not alarms:
        print("No alarms. Add one with: alarm add 07:30")
        return 0

    rows = []
    for a in alarms:
        if not a.enabled or a.next_fire is None:
            status, nxt = "off", "-"
        else:
            status = "snoozed" if a.snoozed else "on"
            nxt = f"{a.next_fire:%a %d %b %H:%M} ({describe_delta(a.next_fire - now)})"
        rows.append((a.id, a.time_str, a.repeat_str, a.label or "-", nxt, status))

    headers = ("ID", "TIME", "REPEAT", "LABEL", "NEXT", "STATUS")
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    for row in rows:
        print(fmt.format(*row))
    return 0


def cmd_remove(args: argparse.Namespace, store: AlarmStore, clock: Clock | None = None) -> int:
    alarms = store.load()
    alarm = find_alarm(alarms, args.id)
    alarms.remove(alarm)
    store.save(alarms)
    print(f"Removed {alarm.id}: {_describe(alarm)}")
    return 0


def cmd_enable(args: argparse.Namespace, store: AlarmStore, clock: Clock | None = None) -> int:
    now = (clock or _now)()
    alarms = store.load()
    alarm = find_alarm(alarms, args.id)
    alarm.enabled = True
    alarm.snoozed = False
    alarm.auto_snoozes = 0
    alarm.next_fire = first_fire_for(alarm, now)
    store.save(alarms)
    print(f"Enabled {alarm.id}: {_describe(alarm)}; fires {alarm.next_fire:%a %d %b %H:%M} "
          f"({describe_delta(alarm.next_fire - now)})")
    return 0


def cmd_disable(args: argparse.Namespace, store: AlarmStore, clock: Clock | None = None) -> int:
    alarms = store.load()
    alarm = find_alarm(alarms, args.id)
    alarm.enabled = False
    alarm.snoozed = False
    alarm.auto_snoozes = 0
    store.save(alarms)
    print(f"Disabled {alarm.id}: {_describe(alarm)}")
    return 0


def cmd_run(args: argparse.Namespace, store: AlarmStore, clock: Clock | None = None) -> int:
    config = RunnerConfig(
        ring_seconds=args.ring_seconds,
        grace_seconds=args.grace_seconds,
        max_auto_snoozes=args.max_auto_snoozes,
    )
    runner = Runner(
        store=store,
        ringer=default_ringer(silent=args.silent),
        input_source=StdinInput(),
        clock=clock or _now,
        config=config,
    )
    return runner.run(once=args.once)


def _describe(alarm: Alarm) -> str:
    text = f"{alarm.time_str} {alarm.repeat_str}"
    return f"{text} \"{alarm.label}\"" if alarm.label else text


# -- parser ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alarm",
        description="A terminal alarm clock. Define alarms with add/list/remove, "
                    "then leave `alarm run` open in a terminal to ring them.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--store", metavar="PATH",
                        help="alarm file (default: $ALARMCLOCK_HOME/alarms.json or ~/.alarmclock/alarms.json)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="add an alarm",
                       description="Examples: alarm add 07:30 -r weekdays -l Stand-up | alarm add 7pm | alarm add +20m -l Tea")
    p.add_argument("when", help="time of day (07:30, 7:30pm, 7am) or relative (+10m, +1h30m)")
    p.add_argument("-l", "--label", help="what this alarm is for")
    p.add_argument("-r", "--repeat", help="once (default), daily, weekdays, weekends, or mon,wed,fri")
    p.add_argument("--snooze", type=int, default=5, metavar="MIN", help="snooze length in minutes (default 5)")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="show alarms and when they fire next")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("remove", help="delete an alarm", aliases=["rm"])
    p.add_argument("id", help="alarm id or unique prefix")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("enable", help="switch an alarm on (reschedules it from now)")
    p.add_argument("id")
    p.set_defaults(func=cmd_enable)

    p = sub.add_parser("disable", help="switch an alarm off without deleting it")
    p.add_argument("id")
    p.set_defaults(func=cmd_disable)

    p = sub.add_parser("run", help="stay in the foreground and ring alarms when due")
    p.add_argument("--ring-seconds", type=int, default=60, metavar="N",
                   help="how long to ring before auto-snoozing (default 60)")
    p.add_argument("--grace-seconds", type=int, default=600, metavar="N",
                   help="alarms more overdue than this are reported missed, not rung (default 600)")
    p.add_argument("--max-auto-snoozes", type=int, default=3, metavar="N",
                   help="unanswered rings before giving up on an alarm (default 3)")
    p.add_argument("--silent", action="store_true", help="no sound, just the banner")
    p.add_argument("--once", action="store_true", help="exit after the first alarm is handled")
    p.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = AlarmStore(args.store) if args.store else AlarmStore(AlarmStore.default_path())
    try:
        return args.func(args, store)
    except (TimeParseError, AlarmNotFound, AmbiguousAlarmId, StoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

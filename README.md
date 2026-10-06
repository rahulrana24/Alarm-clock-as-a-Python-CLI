# alarmclock

A terminal alarm clock in Python. No dependencies, no database, no daemon: you
define alarms with short commands and leave `alarm run` open in a terminal to
ring them.

```
$ alarm add 07:30 -r weekdays -l "Stand-up"
Added 3e1a: 07:30 weekdays "Stand-up"; fires Wed 07 Oct 07:30 (in 9h 12m)

$ alarm add +20m -l Tea
Added 9c04: 22:38 once "Tea"; fires Tue 06 Oct 22:38 (in 20m)

$ alarm list
ID    TIME   REPEAT    LABEL     NEXT                           STATUS
9c04  22:38  once      Tea       Tue 06 Oct 22:38 (in 19m)      on
3e1a  07:30  weekdays  Stand-up  Wed 07 Oct 07:30 (in 9h 11m)   on

$ alarm run
Alarm clock running, watching /Users/you/.alarmclock/alarms.json. Ctrl-C to quit.

================================================
  ALARM  22:38  Tea
  [Enter] dismiss   [s + Enter] snooze 5m
================================================
Alarm 9c04: dismissed; switched off.
```

## Install

Python 3.10 or newer. Nothing else.

```bash
pip install .            # gives you the `alarm` command
```

or run it straight from the checkout without installing:

```bash
python3 -m alarmclock --help
```

## Commands

| Command | What it does |
|---------|--------------|
| `alarm add <when> [-l LABEL] [-r REPEAT] [--snooze MIN]` | `<when>` is a time of day (`07:30`, `7:30pm`, `7am`) or relative (`+10m`, `+1h30m`). `REPEAT` is `daily`, `weekdays`, `weekends`, or `mon,wed,fri`. |
| `alarm list` | Every alarm with when it fires next. |
| `alarm remove <id>` | Delete. Ids accept a unique prefix. |
| `alarm disable <id>` / `alarm enable <id>` | Switch off without deleting; enable reschedules from now. |
| `alarm run [--silent] [--once] [--ring-seconds N] [--grace-seconds N]` | Foreground loop that rings alarms when due. |

While an alarm rings: **Enter** dismisses, **s** then Enter snoozes.
If nobody answers for 60 seconds it auto-snoozes, up to three times, then gives up
and reports the alarm as missed.

Alarms live in `~/.alarmclock/alarms.json` (override with `--store PATH` or
`ALARMCLOCK_HOME`). You can add or remove alarms from another terminal while
`alarm run` is up; it re-reads the file every second.

## Try it in under a minute

```bash
python3 -m alarmclock --store demo-alarms.json add +1m -l "Demo"
python3 -m alarmclock --store demo-alarms.json run --once --ring-seconds 15
```

## How it works

Read the docs in order, they are the design record for the one-hour build:

- [docs/01-requirements.md](docs/01-requirements.md): what an alarm clock has to
  do, what was cut, and the decisions taken before any code.
- [docs/02-design.md](docs/02-design.md): module layout, the `next_fire` state
  machine, keyboard handling, persistence and time handling.
- [docs/03-plan.md](docs/03-plan.md): the time-boxed build order and the review
  checklist applied to generated code.
- [docs/04-process.md](docs/04-process.md): how AI was directed and what was
  caught in review.

The short version: an alarm's state is **the next instant it must ring**
(`next_fire`). Dismiss, snooze, repeat and "missed" are all transitions on that
one field. `models`, `timeparse` and `scheduler` are pure and take `now` as an
argument, so the whole ring/snooze/timeout/grace-window machine is tested with
a fake clock in milliseconds.

```
alarmclock/
  models.py      Alarm record, JSON shape, id lookup
  timeparse.py   "7:30pm" / "+1h30m" / "weekdays" parsing
  scheduler.py   next occurrence maths, snooze/settle transitions
  storage.py     atomic JSON file, read-modify-write of one alarm
  ringer.py      terminal bell, macOS afplay, silent
  runner.py      tick loop, ring state machine, stdin reader thread
  cli.py         argparse surface
tests/           unittest, 47 cases, no real sleeping
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Known limits

- Local time only, naive datetimes. Alarms are wall-clock times on this machine.
- `alarm run` is a foreground process; put it in `tmux` or a spare terminal. If
  it is not running, alarms do not ring. Alarms more than ten minutes overdue
  when it starts are reported as missed, not rung.
- Two alarms due at the same second ring one after the other.
- No file locking. Two commands writing in the same instant could lose one write.
- Sound is the terminal bell plus, on macOS, a system sound via `afplay`. Many
  terminals mute the bell; the banner is the thing you can rely on.

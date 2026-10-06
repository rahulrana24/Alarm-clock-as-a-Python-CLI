# Alarm Clock

A command-line alarm clock in plain Python (no third-party dependencies).
It rings for real: sound, a desktop notification, and a Snooze / Dismiss
dialog on macOS. It can run in the background so alarms fire even when no
terminal is open.

## Install

The easiest way to get a global `alarm` command is uv, which links it into
`~/.local/bin`:

```bash
uv tool install --editable .
```

With pip instead:

```bash
pip install -e .
```

If `alarm` is "not found" after a pip install, pip put the script in a
directory that is not on your PATH (on macOS with python.org Python that is
`~/Library/Python/3.X/bin`). Add that directory to PATH, or use uv.

Without installing, every command below also works as
`python3 -m alarm_clock ...` from this folder.

## Quick start

```bash
alarm add 07:30 --label "Gym" --days weekdays   # create
alarm start                                      # ring alarms in the background
alarm list                                       # see ids, state and next ring
```

When the alarm rings you get a sound, a notification and (on macOS) a dialog
with Snooze and Dismiss buttons. From any terminal you can also run
`alarm snooze 1` or `alarm dismiss 1`.

## Commands

| Command                               | What it does                                                |
| ------------------------------------- | ----------------------------------------------------------- |
| `add TIME [-l LABEL] [-d DAYS] [--once]` | create. TIME like `07:30`, `7:30pm`, `7am`. DAYS: `daily`, `weekdays`, `weekends`, `mon,wed,fri` |
| `edit ID [-t TIME] [-l LABEL] [-d DAYS] [--once / --repeat]` | change an alarm                        |
| `list [--active]`                     | all alarms with id, time, days, state, label, next ring    |
| `delete ID`                           | remove                                                      |
| `activate ID` / `deactivate ID`       | switch on / off                                             |
| `snooze ID [-m MINUTES]`              | only while ringing (default 5 minutes)                      |
| `dismiss ID`                          | silence until the next occurrence                           |
| `ring`                                | which alarms are ringing right now                          |
| `watch`                               | ring alarms in this terminal. Keys: `s` snooze, `d` dismiss, `q` quit |
| `start` / `stop` / `status`           | run `watch` as a background process                         |

`watch` and `start` share options: `--interval SECONDS`, `--snooze MINUTES`,
`--silent` (no sound), `--sound FILE`, `--no-dialog`.

Alarms are saved to `~/.alarm_clock/alarms.json`. Override with
`--store PATH` or the `ALARM_CLOCK_STORE` environment variable. The
background watcher's pid file and log live next to the store.

## How ringing works

An alarm fires at its time on each of its days. It has one of four states:

| State       | Meaning                                                      |
| ----------- | ------------------------------------------------------------ |
| `inactive`  | switched off, never rings                                    |
| `scheduled` | waiting for its next occurrence                              |
| `ringing`   | its time has passed on one of its days and nobody dismissed it yet |
| `snoozed`   | was ringing, will ring again at the snooze time              |

A ringing alarm stays ringing until you snooze or dismiss it. Creating,
editing or activating an alarm whose time already passed today schedules it
for the next occurrence rather than ringing straight away. A `--once` alarm
switches itself off after it is dismissed.

## Layout

```
alarm_clock/
  models.py      Alarm entity and the ringing rules (pure, clock passed in)
  service.py     use cases: create, update, delete, activate, snooze, dismiss
  repository.py  persistence: JSON file store, in-memory store, Protocol
  timefmt.py     parsing "7:30pm" and "mon,wed,fri" style input
  notify.py      OS alerts: macOS / Linux notifications and sound, terminal bell
  inputs.py      how the user reacts while ringing: keyboard keys, macOS dialog
  watcher.py     the loop that polls the service, rings, and applies reactions
  daemon.py      start / stop the watcher as a background process
  cli.py         argparse commands and output
tests/
```

Each layer depends only on the ones below it. `models` and `service` never
touch the OS, so all the scheduling rules are tested with a frozen clock.

## Extending

- **New command**: write a `run_x(app, args)` function (and a
  `configure_x(parser)` if it takes arguments) in `cli.py`, then add one
  `Command(...)` line to `COMMANDS`.
- **New storage backend**: implement `load()` and `save()` from
  `AlarmRepository` in `repository.py` and pass it to `AlarmService`.
- **New way to alert** (Slack, a smart bulb, ...): implement `Notifier` in
  `notify.py` and return it from `make_notifier`.
- **New way to react** (a web button, a hardware switch, ...): implement
  `ReactionSource` in `inputs.py` and add it to the sources in `run_watch`.
- **New input spelling**: add a pattern to `ACCEPTED_FORMATS` or an alias to
  `DAY_ALIASES` in `timefmt.py`.
- **New rule** (date-specific alarms, holidays, ...): extend `Alarm` in
  `models.py`; everything that decides whether an alarm rings lives there.

## Tests

```bash
python -m unittest discover -s tests -v
```

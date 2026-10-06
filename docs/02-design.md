# 02 · Design

## Shape of the system

```
 short-lived commands                 long-lived process
 ┌──────────────────┐                 ┌───────────────────────┐
 │ alarm add/list/  │   JSON file     │ alarm run             │
 │ remove/enable/   │ ─────────────▶  │  tick every second    │
 │ disable          │ ◀─────────────  │  ring due alarms      │
 └──────────────────┘  ~/.alarmclock/ │  dismiss / snooze     │
                        alarms.json   └───────────────────────┘
```

Both sides talk only through the store. The runner re-reads the file every tick
(it is a few hundred bytes), so there is no cache to invalidate and an alarm added
from another terminal is visible within a second.

## Modules

| Module | Responsibility | Depends on |
|--------|---------------|------------|
| `models.py` | `Alarm` dataclass, (de)serialisation, id matching | stdlib |
| `timeparse.py` | `"7:30pm"` → `time`, `"+1h30m"` → `timedelta`, `"weekdays"` → day set | stdlib |
| `scheduler.py` | pure functions: next occurrence of HH:MM on allowed days after an instant | `models` |
| `storage.py` | load/save the JSON file atomically; `update(id, fn)` read-modify-write | `models` |
| `ringer.py` | make noise: terminal bell, macOS `afplay`, or silent | stdlib |
| `runner.py` | the tick loop and the ring state machine | all of the above |
| `cli.py` | argparse surface, formatting, exit codes | all of the above |

Rule: `models`, `timeparse`, `scheduler` do no IO and take `now` as an argument.
That is what makes them testable without sleeping or patching `datetime`.

## The `Alarm` record

```json
{
  "id": "a3f9",
  "hour": 7, "minute": 30,
  "label": "Stand-up",
  "days": [0, 1, 2, 3, 4],          // Python weekday numbers; [] means one-shot
  "enabled": true,
  "snooze_minutes": 5,
  "next_fire": "2026-10-07T07:30:00", // ISO 8601, local naive
  "snoozed": false,
  "auto_snoozes": 0
}
```

`next_fire` is the state. Everything the runner does is a transition on it:

```
             ┌─────────────── dismiss (repeating) ───────────────┐
             ▼                                                   │
  next_fire = next occurrence ──due──▶ RINGING ──dismiss (once)──▶ enabled=false
             ▲                           │
             │                           ├── snooze ──▶ next_fire = now + snooze_minutes
             │                           │
             └── timeout, auto_snoozes<3 ┘
                 timeout, auto_snoozes≥3 ──▶ treated as dismiss, reported "missed"

  overdue by > grace (laptop was asleep) ──▶ reported "missed", then same as dismiss
```

## Ringing and keyboard input

The runner needs to beep once a second **and** notice a keypress. Blocking
`input()` would stop the beeping. Options considered:

- `select()` on stdin: clean on Unix, not on Windows.
- `curses`: heavyweight, hijacks the terminal.
- A daemon thread that calls `sys.stdin.readline()` and pushes lines into a
  `queue.Queue`; the ring loop polls the queue with `get_nowait()`. Cross-platform,
  about fifteen lines. **Chosen.**

The thread is started once per `run` and the queue is drained when ringing
starts, so a stray Enter pressed an hour ago does not dismiss the alarm.

## Sound

`\a` (BEL) is the only thing guaranteed in a terminal, and many terminals mute it.
On macOS the runner also spawns `afplay` on a system sound, non-blocking, best
effort. `--silent` turns all of it off (used in tests and when recording a demo
without the noise). The ringer is an interface so the runner tests use a fake
that counts beeps.

## Persistence

- Path: `$ALARMCLOCK_HOME/alarms.json`, default `~/.alarmclock/`, overridable with
  `--store` for tests and demos.
- Atomic save: write to a temp file in the same directory, then `os.replace`.
  A crash mid-write never leaves a half-written file.
- The runner never holds the alarm list across a ring. After ringing it does
  `store.update(alarm.id, mutate)`: reload, mutate that one record, save. So an
  `add` from another terminal during a 60-second ring is not clobbered.
- No file locking. Two writers in the same millisecond could lose one write. For
  a personal alarm clock that is an accepted trade-off and is documented.

## Time handling

- All datetimes are local and naive. Comparing naive datetimes from `datetime.now()`
  with stored ISO strings is consistent as long as nobody mixes in aware values,
  which the codebase does not.
- Next occurrence: start from `after` with the time replaced by HH:MM, step
  forward day by day (at most 8 steps) until the candidate is strictly after
  `after` and its weekday is allowed.
- Relative alarms (`+10m`) store the exact `next_fire` with seconds intact; a
  one-minute nap timer should not fire 40 seconds early because of rounding.
- Relative durations must be under 24 hours. Beyond that "set it for a time of
  day" is the right tool and the one-shot semantics would be surprising.

## CLI surface

```
alarm add <when> [-l LABEL] [-r REPEAT] [--snooze MIN]
alarm list
alarm remove <id>
alarm enable <id> | disable <id>
alarm run [--ring-seconds N] [--grace-seconds N] [--silent] [--once]
```

`<id>` accepts a unique prefix. `--once` makes `run` exit after the first alarm
is handled, which keeps demos and smoke tests short.

Exit codes: 0 ok, 1 user error (bad time, unknown id), 2 argparse usage error.

## Things deliberately not built

Daemonising, notifications via `osascript`, timezones, overlapping alarms ringing
at once, config files, colours. Each is a sensible next step and none of them
changes the core state machine.

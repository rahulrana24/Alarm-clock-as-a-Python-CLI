# 01 · Requirements

Time budget: one hour, end to end. The brief gives no spec, so the first job is to
decide what "alarm clock" means for a CLI and what to leave out.

## Problem framing

An alarm clock has three jobs:

1. Let me say *when* I want to be interrupted (and how often).
2. Interrupt me at that time in a way I cannot miss.
3. Let me respond (dismiss or snooze) without thinking.

Everything else (labels, listing, enable/disable) exists only to make those three
jobs manageable once you have more than one alarm.

A CLI alarm clock has one structural problem a phone does not: the CLI process is not
always running. So the design must separate **defining** alarms (short-lived
commands) from **ringing** them (a long-lived foreground process), and the two
must agree on a single source of truth on disk.

## User stories (in priority order)

| # | Story | Must / Should / Won't |
|---|-------|-----------------------|
| 1 | Set an alarm for a time of day (`07:30`, `7:30pm`, `7am`) | Must |
| 2 | Set an alarm relative to now (`+10m`, `+1h30m`) for naps and timers | Must |
| 3 | Run a process that rings when an alarm is due | Must |
| 4 | Dismiss or snooze a ringing alarm from the keyboard | Must |
| 5 | List alarms with when each fires next | Must |
| 6 | Remove, enable, disable an alarm | Must |
| 7 | Repeat on a schedule: daily, weekdays, weekends, specific days | Should |
| 8 | Label an alarm | Should |
| 9 | Add an alarm from another terminal while the runner is up, and have it picked up | Should |
| 10 | Survive the laptop being asleep when an alarm was due (don't ring stale alarms hours late) | Should |
| 11 | Sound beyond the terminal bell on macOS | Should (best effort) |
| 12 | Background daemon / launchd / systemd integration | Won't |
| 13 | Multiple concurrent ringing alarms | Won't (ring them one after another) |
| 14 | Timezone selection | Won't (local time only) |
| 15 | Natural language ("tomorrow at nine") | Won't |

## Constraints from the brief

- Python, CLI only. No web UI, no React, no database.
- "No database" is read as: no SQLite, no server. A JSON file is state, not a database.

## Decisions made before writing code

- **Zero runtime dependencies.** The thing has to run with `python3 -m alarmclock`
  on a clean machine. argparse, json, dataclasses, threading and datetime cover it.
  The tests use `unittest` for the same reason (pytest will still run them).
- **Local naive time.** Alarms are "07:30 wall-clock time wherever this machine
  is". No timezone plumbing. DST is handled the way a bedside clock handles it:
  the alarm fires at 07:30 on the clock, whatever the offset.
- **Persist `next_fire`, don't recompute it from the spec each tick.** This is the
  single most important design choice. An alarm's state is "the next instant it
  must ring". Snooze, repeat, and one-shot all become "set `next_fire` to X".
  It also makes `list` honest: it shows the stored value the runner will act on.
- **The runner is a foreground process.** It is what you would `tmux` or leave in
  a terminal. Daemonising is out of scope and would double the surface area.
- **Keyboard protocol while ringing:** `Enter` dismisses, `s` + `Enter` snoozes.
  The default must be the action you want when half-asleep, and that is dismiss.
- **Ringing times out.** A real alarm clock stops after a minute and auto-snoozes.
  Default: ring for 60 s, auto-snooze up to 3 times, then give up and mark it missed.
- **Grace window for late alarms.** If the runner wakes up (laptop lid opened) and
  an alarm is more than 10 minutes overdue, it is reported as missed and rescheduled
  rather than rung. Ringing a 07:00 alarm at 11:40 helps nobody.

## Acceptance checks (what "done" means in an hour)

- `alarm add 07:30 -r weekdays -l "Stand-up"` then `alarm list` shows it with a
  correct next-fire in the future on a weekday.
- `alarm add +1m` then `alarm run` rings within a minute; `Enter` stops it; the
  alarm is disabled afterwards.
- `s` + `Enter` while ringing reschedules it `snooze_minutes` later and `list` shows that.
- Adding an alarm from a second terminal while `run` is active gets picked up.
- Unit tests cover time parsing, next-occurrence maths, persistence round-trip, and
  the ring/snooze/dismiss/timeout/missed state machine with a fake clock.

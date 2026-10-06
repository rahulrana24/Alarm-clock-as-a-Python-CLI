# 03 · Implementation plan

Sixty minutes. The order is chosen so that at any cut-off point there is a
working, testable artefact.

| Slot | Minutes | Build | Verify |
|------|---------|-------|--------|
| 0 | 0–10 | Requirements and design docs (this folder) | Re-read: does every "Must" story have a module that owns it? |
| 1 | 10–20 | `models.py`, `timeparse.py`, `scheduler.py` + their tests | `python -m unittest` green. These are pure, so tests are cheap and precise. |
| 2 | 20–30 | `storage.py` (atomic save, `update`) + test; `cli.py` with `add`/`list`/`remove`/`enable`/`disable` | Manual: add three alarms, list, remove one, list. |
| 3 | 30–45 | `ringer.py`, `runner.py` with the state machine + runner test using fake clock, fake ringer, scripted input | Test covers: fires when due, dismiss disables one-shot, dismiss reschedules repeating, snooze, timeout auto-snooze cap, grace window. |
| 4 | 45–50 | `run` subcommand wired, stdin reader thread, `--once`, `--silent` | Live: `alarm add +1m`, `alarm run --once`, press Enter. Second terminal `add` while running. |
| 5 | 50–60 | README, `pyproject.toml`, git init, final test run | `python -m unittest -v`, `python -m alarmclock --help`. |

## Review checklist applied to AI output

Each generated module is read against these questions before it is kept:

1. Does any function in `models`/`timeparse`/`scheduler` call `datetime.now()` or
   touch disk? (Must be no, or the tests cannot control time.)
2. Does the runner ever hold the alarm list across a blocking ring and then save
   it? (Must be no, or concurrent `add` is lost.)
3. Is `next_fire` ever recomputed from `hour`/`minute` outside a state transition?
   (Must be no, or snooze would be silently undone.)
4. What happens at exactly `next_fire == now`? (Fires: comparison is `<=`.)
5. What happens on the 8th candidate day in `next_occurrence`? (Unreachable with a
   non-empty day set; raise rather than loop.)
6. Can a stray keypress before ringing dismiss the alarm? (No: queue drained at ring start.)
7. What does a bare `7` parse to? (Error. Ambiguous input is rejected, not guessed.)

## Cut list, if time runs out

In this order: macOS sound → specific-day repeats → enable/disable → labels.
The state machine, persistence and the dismiss/snooze loop are never cut.

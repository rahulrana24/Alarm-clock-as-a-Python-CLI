# 04 · Process notes: how AI was used

The brief asks to see how problems were defined, how AI was directed, how its
output was reviewed and how the result was validated. This is that record,
written during the build.

## 1. Define the problem before touching code

The first prompt to the assistant was the brief itself plus one instruction:
*refine requirements, design and plan before writing code*. That produced
`01-requirements.md` through `03-plan.md`. Three decisions from that pass drove
everything after:

- Split **defining** alarms (short commands) from **ringing** them (a foreground
  loop), joined by one JSON file. The CLI process is not always alive; pretending
  otherwise is the classic mistake in a CLI alarm clock.
- Make **`next_fire` the state**. Snooze, repeat, one-shot and "missed" are all
  writes to one field. Everything stays explainable in a sentence.
- Keep **pure modules pure**. Parsing and scheduling take `now` as an argument so
  the tests never sleep or patch `datetime`.

## 2. Direct the AI in module-sized pieces, in dependency order

Models and parsing first, then scheduler, storage, ringer, runner, CLI. Each
piece was requested with its responsibility and its boundary stated ("no IO, no
clock") rather than "write an alarm clock". That keeps generated code reviewable
in one screen.

## 3. Review the output against a checklist, not a vibe

The checklist is in `03-plan.md`. What it caught:

- **Runner must not hold the alarm list across a ring.** The first draft loaded,
  rang, then saved the whole list. An `alarm add` from a second terminal during
  the 60-second ring would have been overwritten. Replaced with
  `store.update(id, mutate)`: reload, change one record, save. A test
  (`test_alarm_added_during_ring_is_kept`) pins it.
- **Stale keypresses.** The stdin reader thread queues every line typed, so an
  Enter pressed an hour ago would have dismissed the next alarm instantly. The
  queue is now drained when ringing starts; a test pins that too.
- **Bare `7` as a time.** Early parser accepted it as 07:00. Rejected instead:
  ambiguous input should fail loudly, not guess.
- **Relative alarms over 24 h.** Allowed in the first draft; the one-shot
  semantics would silently fire a day early. Now an error.

## 4. Validate with tests that control time, then with a real terminal

- 47 unit tests across parsing, scheduling maths, persistence, the ring state
  machine and the CLI. The runner tests use a fake clock whose `sleep` advances
  time, so a 60-second ring timeout runs in a millisecond.
- The test run found two real defects in generated code:
  1. The CLI commands took `clock=datetime.now` as a default argument. Defaults
     bind at import time, so the test's patch had no effect and the tests used
     the wall clock. Fix: resolve the clock inside the function. Lesson: a seam
     for time has to be a call, not a default value.
  2. When the auto-snooze budget was spent the runner printed "timed out;
     switched off" without saying the alarm was missed. The test asserted on the
     word "missed" and failed. The message now says so explicitly.
- A live smoke test with the real `run` loop: add three alarms, force one due,
  run `--once`, press Enter after the banner appears. First attempt piped Enter
  on stdin *before* the banner and the drain logic correctly discarded it, which
  was the design working as intended rather than a bug. Second attempt sent
  Enter after a two-second delay and dismissed the alarm; `list` showed it off.

## 5. What was cut and why

Daemonising, desktop notifications, timezones and file locking were all left
out deliberately (see `01-requirements.md`). Each is an afternoon of work that
does not change the core state machine, and the hour was better spent making the
state machine correct and tested.

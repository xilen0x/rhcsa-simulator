# Feature: interactive-menu

## Objective
Make `rhcsa-sim` simpler and more visually attractive: an interactive menu with short commands to move between exercises, grade the current exercise, or grade all of them.

## Problem / why
Today the user must type full subcommands (`rhcsa-sim check users-01`) per task and remember task ids. Output is plain `[OK]/[KO]` lines.

## Scope
- `rhcsa-sim` with no arguments opens an interactive session (existing `list`/`show`/`check` subcommands stay unchanged for scripting).
- Session shows a banner, the current exercise in a box, and a command bar.
- Short commands: `n`/Enter next, `p` previous, `<number>` or `<task-id>` jump, `c` grade current, `a` grade all, `l` list with per-task status, `h` help, `q` quit.
- Session remembers results to show progress (passed/failed/pending) and a running score.
- Visual primitives: boxes, symbols, progress bar, colors; ASCII fallback when stdout is not UTF-8; color rules unchanged (`NO_COLOR`, `TERM=dumb`, TTY).

## Constraints
- stdlib only, Python 3.12, mypy strict clean, all text from the system via `sanitize_text`.
- CLI output in English, comments/docstrings in Spanish (project convention).
- Input/output injectable for tests (no real TTY needed).

## Acceptance criteria
- No-arg run enters the menu; EOF or `q` exits with code 0.
- Navigation wraps within bounds (no crash at first/last task); unknown command shows a hint.
- `c` grades only the current task; `a` grades all and prints the summary.
- All existing tests still pass.

## TDD
Mode: enabled (source: user global CLAUDE.md "Strict TDD Mode: enabled"). Runner: `.venv/bin/pytest`. Type check: `.venv/bin/mypy src tests`.

## Delivery
Strategy: ask-on-risk. Forecast: ~450 authored lines (code + tests + docs).

## Tasks
- [x] T1 Visual primitives + interactive session + no-arg entrypoint, with tests (route: delegated writer — 2+ non-trivial files)
- [x] T2 README usage section for the menu (route: inline — one mechanical doc file)

## Progress / evidence
- Baseline: 1347 passed, mypy clean (Python 3.12 venv recreated with uv).

- T1 commit c72fc91: 1373 passed, mypy clean (65 files); piped session smoke test OK (navigation bounds, unknown command, NO_COLOR, exit 0). Writer hand-back report was empty; parent verified state directly.
- T2 commit: README interactive menu section.

## Next step
User decides on push/PR. Native review assessment pending per RDD.

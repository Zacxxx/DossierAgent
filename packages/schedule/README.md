# `schedule`

Scheduling package.

## Owns

- due-watch calculation
- frequency policy
- cron entrypoint behavior
- next-run updates

## Does Not Own

- browser execution
- agent reasoning
- persistence implementation
- frontend timers

## Public Surface

- `find_due_watches`
- `compute_next_run_at`
- `run_due_watches_plan`

## Frequencies

- `hourly`
- `twice_daily`
- `daily`
- `weekly`

The package is pure policy code. It accepts watch-shaped mappings and returns
due-watch plans; `core` owns persistence and the internal HTTP cron route.

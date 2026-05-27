from .policies import compute_next_run_at, find_due_watches, run_due_watches_plan

PACKAGE_MANIFEST = {
    "name": "schedule",
    "concern": "Cron-facing watch scheduling and due-run policy.",
    "owns": (
        "due watch selection",
        "frequency policy",
        "next run calculation",
        "cron entrypoint planning",
    ),
    "exposes": (
        "find_due_watches",
        "compute_next_run_at",
        "run_due_watches_plan",
    ),
    "events": (
        "schedule.watch.due",
        "schedule.watch.skipped",
    ),
}


def get_manifest() -> dict[str, object]:
    return dict(PACKAGE_MANIFEST)

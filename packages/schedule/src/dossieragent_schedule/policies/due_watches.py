from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

SUPPORTED_FREQUENCIES: dict[str, timedelta] = {
    "hourly": timedelta(hours=1),
    "twice_daily": timedelta(hours=12),
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
}
ACTIVE_STATUSES = {"active"}


def find_due_watches(
    watches: Iterable[Mapping[str, Any]],
    *,
    now: str | datetime | None = None,
) -> tuple[dict[str, Any], ...]:
    now_datetime = coerce_utc_datetime(now or datetime.now(UTC))
    due_watches: list[dict[str, Any]] = []

    for watch in watches:
        if not is_active_watch(watch):
            continue

        next_run_at = watch.get("next_run_at")
        if next_run_at is None:
            continue

        if coerce_utc_datetime(str(next_run_at)) <= now_datetime:
            due_watches.append(dict(watch))

    return tuple(due_watches)


def compute_next_run_at(
    frequency: str,
    *,
    from_time: str | datetime | None = None,
) -> str:
    interval = SUPPORTED_FREQUENCIES.get(frequency)
    if interval is None:
        supported = ", ".join(sorted(SUPPORTED_FREQUENCIES))
        raise ValueError(f"Unsupported watch frequency: {frequency}. Supported: {supported}.")

    base_time = coerce_utc_datetime(from_time or datetime.now(UTC))
    return format_utc_datetime(base_time + interval)


def run_due_watches_plan(
    watches: Iterable[Mapping[str, Any]],
    *,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    now_datetime = coerce_utc_datetime(now or datetime.now(UTC))
    due_watches = find_due_watches(watches, now=now_datetime)
    return {
        "now": format_utc_datetime(now_datetime),
        "due_watches": due_watches,
        "due_count": len(due_watches),
    }


def is_active_watch(watch: Mapping[str, Any]) -> bool:
    return str(watch.get("status", "active")) in ACTIVE_STATUSES


def coerce_utc_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_utc_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

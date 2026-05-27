from __future__ import annotations

import unittest

from dossieragent_schedule import compute_next_run_at, find_due_watches, run_due_watches_plan


class DueWatchPolicyTests(unittest.TestCase):
    def test_find_due_watches_uses_active_status_and_next_run_at(self) -> None:
        watches = (
            {"id": "due", "status": "active", "next_run_at": "2026-05-27T10:00:00Z"},
            {"id": "equal", "status": "active", "next_run_at": "2026-05-27T12:00:00Z"},
            {"id": "future", "status": "active", "next_run_at": "2026-05-27T12:01:00Z"},
            {"id": "paused", "status": "paused", "next_run_at": "2026-05-27T10:00:00Z"},
            {"id": "unset", "status": "active", "next_run_at": None},
        )

        due_watches = find_due_watches(watches, now="2026-05-27T12:00:00Z")

        self.assertEqual([watch["id"] for watch in due_watches], ["due", "equal"])

    def test_find_due_watches_normalizes_offsets_to_utc(self) -> None:
        watches = (
            {"id": "paris", "status": "active", "next_run_at": "2026-05-27T14:00:00+02:00"},
        )

        due_watches = find_due_watches(watches, now="2026-05-27T12:00:00Z")

        self.assertEqual([watch["id"] for watch in due_watches], ["paris"])

    def test_compute_next_run_at_supports_expected_frequencies(self) -> None:
        base_time = "2026-05-27T12:00:00Z"

        self.assertEqual(
            compute_next_run_at("hourly", from_time=base_time),
            "2026-05-27T13:00:00Z",
        )
        self.assertEqual(
            compute_next_run_at("twice_daily", from_time=base_time),
            "2026-05-28T00:00:00Z",
        )
        self.assertEqual(
            compute_next_run_at("daily", from_time=base_time),
            "2026-05-28T12:00:00Z",
        )
        self.assertEqual(
            compute_next_run_at("weekly", from_time=base_time),
            "2026-06-03T12:00:00Z",
        )

    def test_compute_next_run_at_rejects_unknown_frequency(self) -> None:
        with self.assertRaises(ValueError):
            compute_next_run_at("monthly", from_time="2026-05-27T12:00:00Z")

    def test_run_due_watches_plan_summarizes_due_selection(self) -> None:
        plan = run_due_watches_plan(
            ({"id": "due", "status": "active", "next_run_at": "2026-05-27T10:00:00Z"},),
            now="2026-05-27T12:00:00Z",
        )

        self.assertEqual(plan["now"], "2026-05-27T12:00:00Z")
        self.assertEqual(plan["due_count"], 1)
        self.assertEqual(plan["due_watches"][0]["id"], "due")


if __name__ == "__main__":
    unittest.main()

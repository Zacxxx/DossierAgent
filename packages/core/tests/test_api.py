from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from dossieragent_database import create_connection
from dossieragent_database.seed import seed_demo_data
from dossieragent_core.api import create_app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "dossieragent-core"})

    def test_openapi_is_available(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["info"]["title"], "DossierAgent API")
        self.assertIn("/health", payload["paths"])

    def test_not_found_uses_spec_error_envelope(self) -> None:
        response = self.client.get("/missing")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "not_found")
        self.assertEqual(payload["error"]["message"], "Route introuvable.")
        self.assertEqual(payload["error"]["details"], {"path": "/missing"})
        self.assertFalse(payload["error"]["retryable"])
        self.assertRegex(payload["error"]["trace_id"], re.compile(r"^trc_[a-f0-9]{12}$"))

    def test_dashboard_reads_seeded_sqlite_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}):
                response = self.client.get("/api/v1/dashboard")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["current_watch"]["id"], "watch_toulouse_t2")
        self.assertEqual(payload["latest_run"]["stats"]["duplicates"], 8)
        self.assertEqual(payload["dossier"]["readiness_score"], 78)
        self.assertEqual(payload["pending_checks"], 3)
        self.assertEqual(payload["notifications_unread"], 5)
        self.assertEqual(len(payload["recommended_listings"]), 4)

    def test_criteria_and_market_watch_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}):
                create_criteria = self.client.post(
                    "/api/v1/criteria",
                    json={
                        "mode": "rent",
                        "cities": ["Lyon"],
                        "districts": ["Croix-Rousse"],
                        "budget_max": 900,
                        "surface_min": 32,
                        "rooms_min": 2,
                        "languages": ["fr"],
                        "filters": {"must_have": ["metro"]},
                    },
                )
                criteria_list = self.client.get("/api/v1/criteria")

                criteria_id = create_criteria.json()["id"]
                create_watch = self.client.post(
                    "/api/v1/market-watches",
                    json={
                        "criteria_id": criteria_id,
                        "name": "Lyon T2",
                        "status": "active",
                        "frequency": "daily",
                        "next_run_at": "2026-05-28T08:00:00Z",
                        "source_config": {"sources": ["manual_urls"]},
                    },
                )
                watch_id = create_watch.json()["id"]
                watch_list = self.client.get("/api/v1/market-watches")
                patch_watch = self.client.patch(
                    f"/api/v1/market-watches/{watch_id}",
                    json={"status": "paused", "frequency": "weekly"},
                )

        self.assertEqual(create_criteria.status_code, 201)
        self.assertEqual(create_criteria.json()["cities"], ["Lyon"])
        self.assertEqual(criteria_list.status_code, 200)
        self.assertIn(criteria_id, {item["id"] for item in criteria_list.json()["items"]})

        self.assertEqual(create_watch.status_code, 201)
        self.assertEqual(create_watch.json()["criteria_id"], criteria_id)
        self.assertEqual(watch_list.status_code, 200)
        self.assertIn(watch_id, {item["id"] for item in watch_list.json()["items"]})
        self.assertEqual(patch_watch.status_code, 200)
        self.assertEqual(patch_watch.json()["status"], "paused")
        self.assertEqual(patch_watch.json()["frequency"], "weekly")


if __name__ == "__main__":
    unittest.main()

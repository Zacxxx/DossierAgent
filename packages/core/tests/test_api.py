from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from dossieragent_database import create_connection
from dossieragent_database.seed import seed_demo_data
from dossieragent_core.auth import (
    AuthenticatedUser,
    AuthSession,
    AuthSignupResult,
    derived_app_user_id,
)
from dossieragent_core.api import create_app


class FakeJsonResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeJsonResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


LISTING_IMPORT_HTML = """
<!doctype html>
<html>
  <head>
    <title>Fallback title</title>
    <link rel="canonical" href="https://demo.example/listings/imported-t2?tracking=1" />
    <meta name="description" content="T2 proche metro avec contact agence." />
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Apartment",
        "name": "T2 Import Carmes proche metro",
        "description": "Appartement lumineux avec balcon.",
        "url": "https://demo.example/listings/imported-t2",
        "image": ["https://cdn.demo.example/listings/imported-t2.jpg"],
        "sku": "imported-t2",
        "numberOfRooms": 2,
        "floorSize": {"@type": "QuantitativeValue", "value": 41, "unitCode": "MTK"},
        "offers": {"@type": "Offer", "price": "795", "priceCurrency": "EUR"},
        "address": {
          "@type": "PostalAddress",
          "addressLocality": "Toulouse",
          "addressRegion": "Carmes",
          "postalCode": "31000"
        },
        "seller": {"@type": "RealEstateAgent", "name": "Agence Import Demo"}
      }
    </script>
  </head>
  <body>
    <main>
      <h1>T2 Import Carmes proche metro</h1>
      <p>41 m2 - 2 pieces - contact agence.</p>
    </main>
  </body>
</html>
"""


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

    def test_supabase_login_refresh_and_me_contract(self) -> None:
        fake_client = FakeAuthClient()

        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "dossieragent.db"
            with (
                patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}),
                patch("dossieragent_core.api.build_auth_client", return_value=fake_client),
            ):
                login_response = self.client.post(
                    "/api/v1/auth/login",
                    json={"email": "demo@example.com", "password": "correct-password"},
                )
                refresh_response = self.client.post(
                    "/api/v1/auth/refresh",
                    json={"refresh_token": "refresh_token_123"},
                )
                missing_me_response = self.client.get("/api/v1/me")
                me_response = self.client.get(
                    "/api/v1/me",
                    headers={"Authorization": "Bearer access_token_123"},
                )

        self.assertEqual(login_response.status_code, 200)
        login_payload = login_response.json()
        self.assertEqual(login_payload["access_token"], "access_token_123")
        self.assertEqual(login_payload["refresh_token"], "refresh_token_123")
        self.assertEqual(login_payload["token_type"], "bearer")
        self.assertEqual(login_payload["user"]["provider"], "supabase")
        self.assertEqual(login_payload["user"]["app_user_id"], "usr_demo")
        self.assertEqual(login_payload["user"]["email"], "demo@example.com")

        self.assertEqual(refresh_response.status_code, 200)
        self.assertEqual(refresh_response.json()["access_token"], "access_token_refreshed")
        self.assertEqual(missing_me_response.status_code, 401)
        self.assertEqual(missing_me_response.json()["error"]["code"], "authentication_required")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["app_user_id"], "usr_demo")

    def test_supabase_register_forgot_password_and_logout_contract(self) -> None:
        fake_client = FakeAuthClient()

        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "dossieragent.db"
            with (
                patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}),
                patch("dossieragent_core.api.build_auth_client", return_value=fake_client),
            ):
                register_response = self.client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": "new@example.com",
                        "password": "correct-password",
                        "display_name": "New User",
                        "redirect_to": "http://localhost:5173/auth",
                    },
                )
                forgot_response = self.client.post(
                    "/api/v1/auth/password/forgot",
                    json={"email": "new@example.com", "redirect_to": "http://localhost:5173/auth"},
                )
                logout_response = self.client.post(
                    "/api/v1/auth/logout",
                    headers={"Authorization": "Bearer access_token_123"},
                )
                local_logout_response = self.client.post("/api/v1/auth/logout")

        self.assertEqual(register_response.status_code, 201)
        self.assertEqual(register_response.json()["status"], "session_created")
        self.assertEqual(register_response.json()["session"]["access_token"], "access_token_registered")
        self.assertEqual(register_response.json()["user"]["email"], "new@example.com")
        self.assertEqual(fake_client.register_payload["display_name"], "New User")
        self.assertEqual(fake_client.recover_payload["email"], "new@example.com")
        self.assertEqual(fake_client.logout_token, "access_token_123")
        self.assertEqual(forgot_response.status_code, 200)
        self.assertEqual(forgot_response.json(), {"status": "recovery_requested"})
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json(), {"status": "logged_out"})
        self.assertEqual(local_logout_response.status_code, 200)
        self.assertEqual(local_logout_response.json(), {"status": "logged_out"})

    def test_bearer_token_selects_seeded_user_for_existing_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with (
                patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}),
                patch(
                    "dossieragent_core.api.build_auth_client",
                    return_value=FakeAuthClient(
                        authenticated_user=demo_auth_user(email="demo@dossieragent.local"),
                    ),
                ),
            ):
                response = self.client.get(
                    "/api/v1/dashboard",
                    headers={"Authorization": "Bearer access_token_123"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current_watch"]["id"], "watch_toulouse_t2")

    def test_bearer_token_provisions_new_supabase_user(self) -> None:
        provider_user_id = "supabase_cloud_user_123"
        app_user_id = derived_app_user_id("supabase", provider_user_id)
        auth_user = supabase_auth_user(
            email="cloud@example.com",
            provider_user_id=provider_user_id,
            app_user_id=app_user_id,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "dossieragent.db"
            with (
                patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}),
                patch(
                    "dossieragent_core.api.build_auth_client",
                    return_value=FakeAuthClient(authenticated_user=auth_user),
                ),
            ):
                response = self.client.get(
                    "/api/v1/me",
                    headers={"Authorization": "Bearer access_token_123"},
                )

            connection = create_connection(database_path)
            try:
                row = connection.execute("SELECT * FROM users WHERE id = ?", (app_user_id,)).fetchone()
            finally:
                connection.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["app_user_id"], app_user_id)
        self.assertNotEqual(response.json()["app_user_id"], "usr_demo")
        self.assertIsNotNone(row)
        self.assertEqual(row["email"], "cloud@example.com")

    def test_authenticated_cloud_user_is_isolated_from_seeded_demo_data(self) -> None:
        provider_user_id = "supabase_cloud_user_456"
        app_user_id = derived_app_user_id("supabase", provider_user_id)
        auth_user = supabase_auth_user(
            email="isolated@example.com",
            provider_user_id=provider_user_id,
            app_user_id=app_user_id,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with (
                patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}),
                patch(
                    "dossieragent_core.api.build_auth_client",
                    return_value=FakeAuthClient(authenticated_user=auth_user),
                ),
            ):
                response = self.client.get(
                    "/api/v1/dashboard",
                    headers={"Authorization": "Bearer access_token_123"},
                )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "dashboard_not_ready")
        self.assertEqual(response.json()["error"]["details"]["user_id"], app_user_id)

    def test_auth_required_rejects_demo_header_without_bearer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_AUTH_REQUIRED": "true",
                },
            ):
                response = self.client.get(
                    "/api/v1/dashboard",
                    headers={"X-Demo-User-Id": "usr_demo"},
                )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")

    def test_auth_metadata_conflict_is_rejected(self) -> None:
        conflicting_user = demo_auth_user(email="attacker@example.com")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with (
                patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}),
                patch(
                    "dossieragent_core.api.build_auth_client",
                    return_value=FakeAuthClient(authenticated_user=conflicting_user),
                ),
            ):
                response = self.client.get(
                    "/api/v1/me",
                    headers={"Authorization": "Bearer access_token_123"},
                )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "auth_user_conflict")

    def test_login_requires_supabase_configuration(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "DOSSIERAGENT_SUPABASE_URL": "",
                "DOSSIERAGENT_SUPABASE_ANON_KEY": "",
            },
            clear=False,
        ):
            response = self.client.post(
                "/api/v1/auth/login",
                json={"email": "demo@example.com", "password": "correct-password"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "auth_not_configured")

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
        self.assertEqual(payload["dossier"]["missing_docs"], ["employment_contract", "latest_tax_notice"])
        self.assertEqual(payload["pending_checks"], 3)
        self.assertEqual(payload["notifications_unread"], 5)
        self.assertEqual(len(payload["recommended_listings"]), 4)
        self.assertEqual(
            payload["recommended_listings"][0]["image_urls"],
            [
                "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=900&q=80"
            ],
        )
        self.assertEqual(
            payload["recommended_listings"][0]["source_url"],
            "https://demo.dossieragent.local/listings/001",
        )

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

    def test_run_now_lifecycle_respects_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}):
                first_run = self.client.post(
                    "/api/v1/market-watches/watch_toulouse_t2/run-now",
                    headers={"Idempotency-Key": "run-now-test-key"},
                )
                replayed_run = self.client.post(
                    "/api/v1/market-watches/watch_toulouse_t2/run-now",
                    headers={"Idempotency-Key": "run-now-test-key"},
                )
                connection = create_connection(database_path)
                try:
                    connection.execute(
                        """
                        INSERT INTO agent_runs (
                            id, user_id, watch_id, trigger_type, intent, status, current_step,
                            summary_json, error_json, created_at, updated_at, completed_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "run_active_test",
                            "usr_demo",
                            "watch_toulouse_t2",
                            "manual",
                            "run_market_watch",
                            "running",
                            "source_scan",
                            "{}",
                            None,
                            "2026-05-31T00:00:00Z",
                            "2026-05-31T00:00:00Z",
                            None,
                        ),
                    )
                    connection.commit()
                finally:
                    connection.close()
                conflicting_run = self.client.post(
                    "/api/v1/market-watches/watch_toulouse_t2/run-now",
                    headers={"Idempotency-Key": "different-key"},
                )
                run_id = first_run.json()["run_id"]
                run_detail = self.client.get(f"/api/v1/agent-runs/{run_id}")
                run_events = self.client.get(f"/api/v1/agent-runs/{run_id}/events")
                listings = self.client.get("/api/v1/listings?q=Filatiers")
                dashboard = self.client.get("/api/v1/dashboard")
                notifications = self.client.get("/api/v1/notifications")

        self.assertEqual(first_run.status_code, 202)
        self.assertEqual(first_run.json()["status"], "completed")
        self.assertFalse(first_run.json()["idempotent_replay"])
        self.assertEqual(first_run.json()["summary"]["candidate_count"], 3)
        self.assertEqual(first_run.json()["summary"]["new_count"], 1)
        self.assertEqual(first_run.json()["summary"]["duplicate_count"], 1)
        self.assertEqual(first_run.json()["summary"]["repost_count"], 1)
        self.assertEqual(first_run.json()["summary"]["search_index"]["reason"], "elastic_not_configured")
        self.assertEqual(replayed_run.status_code, 202)
        self.assertEqual(replayed_run.json()["run_id"], first_run.json()["run_id"])
        self.assertTrue(replayed_run.json()["idempotent_replay"])
        self.assertEqual(conflicting_run.status_code, 409)
        self.assertEqual(conflicting_run.json()["error"]["code"], "run_already_active")
        self.assertEqual(run_detail.status_code, 200)
        self.assertEqual(run_detail.json()["id"], run_id)
        self.assertEqual(run_detail.json()["current_step"], "completed")
        self.assertEqual(run_events.status_code, 200)
        self.assertEqual(
            [event["type"] for event in run_events.json()["items"]],
            [
                "run_accepted",
                "source_scan_started",
                "source_scan_finished",
                "normalized",
                "deduped",
                "ranked",
                "index_skipped",
                "notifications_created",
                "completed",
            ],
        )
        self.assertEqual(listings.status_code, 200)
        self.assertGreaterEqual(listings.json()["total"], 1)
        self.assertEqual(listings.json()["items"][0]["title"], "Deux pieces renove rue des Filatiers")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(
            "Deux pieces renove rue des Filatiers",
            {item["title"] for item in dashboard.json()["recommended_listings"]},
        )
        self.assertEqual(notifications.status_code, 200)
        self.assertEqual(notifications.json()["items"][0]["type"], "watch_run_completed")

    def test_run_now_indexes_watch_listings_when_elastic_is_configured(self) -> None:
        captured_requests = []

        def fake_urlopen(request: object, timeout: int) -> FakeUrlopenResponse:
            captured_requests.append((request, timeout))
            payload = request.data.decode("utf-8")  # type: ignore[attr-defined]
            lines = [json.loads(line) for line in payload.splitlines()]
            action_lines = lines[0::2]
            return FakeUrlopenResponse(
                {
                    "errors": False,
                    "items": [
                        {"index": {"_id": action["index"]["_id"], "status": 201}}
                        for action in action_lines
                    ],
                }
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with (
                patch.dict(
                    "os.environ",
                    {
                        "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                        "DOSSIERAGENT_ELASTIC_URL": "http://elastic.local:9200",
                        "DOSSIERAGENT_ELASTIC_API_KEY": "elastic-key",
                    },
                ),
                patch("dossieragent_core.api.urllib.request.urlopen", side_effect=fake_urlopen),
            ):
                response = self.client.post("/api/v1/market-watches/watch_toulouse_t2/run-now")

        self.assertEqual(response.status_code, 202)
        search_index = response.json()["summary"]["search_index"]
        self.assertEqual(search_index["status"], "indexed")
        self.assertGreater(search_index["attempted"], 0)
        self.assertEqual(search_index["indexed"], search_index["attempted"])
        self.assertEqual(len(captured_requests), 1)
        request, timeout = captured_requests[0]
        self.assertEqual(timeout, 5)
        self.assertEqual(request.full_url, "http://elastic.local:9200/_bulk")  # type: ignore[attr-defined]
        self.assertIn(b'"listing_id":"lst_001"', request.data)  # type: ignore[attr-defined]
        self.assertEqual(request.get_header("Authorization"), "ApiKey elastic-key")  # type: ignore[attr-defined]

    def test_run_now_records_failed_browser_extraction(self) -> None:
        blocked_source_config = {
            "sources": [
                {
                    "source": "demo_seed",
                    "mode": "list_page",
                    "url": "https://demo.dossieragent.local/search/blocked",
                    "html": "<html><body>captcha required</body></html>",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
                before_count = connection.execute("SELECT COUNT(*) AS count FROM listings").fetchone()["count"]
                connection.execute(
                    """
                    UPDATE market_watches
                    SET source_config_json = ?
                    WHERE id = ?
                    """,
                    (json.dumps(blocked_source_config), "watch_toulouse_t2"),
                )
                connection.commit()
            finally:
                connection.close()

            with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}):
                response = self.client.post("/api/v1/market-watches/watch_toulouse_t2/run-now")
                run_id = response.json()["run_id"]
                run_detail = self.client.get(f"/api/v1/agent-runs/{run_id}")
                run_events = self.client.get(f"/api/v1/agent-runs/{run_id}/events")

            connection = create_connection(database_path)
            try:
                after_count = connection.execute("SELECT COUNT(*) AS count FROM listings").fetchone()["count"]
            finally:
                connection.close()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(response.json()["summary"]["errors"][0]["code"], "browser_extraction_failed")
        self.assertEqual(run_detail.status_code, 200)
        self.assertEqual(run_detail.json()["status"], "failed")
        self.assertEqual(run_detail.json()["error"]["code"], "browser_extraction_failed")
        self.assertEqual(
            [event["type"] for event in run_events.json()["items"]],
            ["run_accepted", "source_scan_started", "failed"],
        )
        self.assertEqual(after_count, before_count)

    def test_agent_command_rejects_autonomous_external_contact(self) -> None:
        response = self.client.post(
            "/api/v1/agent/commands",
            json={"command": "Envoie un email au proprietaire pour cette annonce"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["intent"], "blocked_external_contact")
        self.assertEqual(payload["action"], "none")
        self.assertIn("no_autonomous_email", payload["guardrails"])
        self.assertIsNone(payload["result"])

    def test_ai_provider_models_are_fetched_without_secret_leakage(self) -> None:
        def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
            url = request.full_url  # type: ignore[attr-defined]
            if url.endswith("/models") and "openai.test" in url:
                return FakeJsonResponse({"data": [{"id": "gpt-live", "owned_by": "openai"}]})
            if url.endswith("/models") and "anthropic.test" in url:
                return FakeJsonResponse(
                    {"data": [{"id": "claude-live", "display_name": "Claude Live"}]}
                )
            if "google.test" in url:
                return FakeJsonResponse(
                    {
                        "models": [
                            {
                                "name": "models/gemini-live",
                                "baseModelId": "gemini-live",
                                "displayName": "Gemini Live",
                                "supportedGenerationMethods": ["generateContent"],
                            }
                        ]
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

        env = {
            "DOSSIERAGENT_OPENAI_API_KEY": "openai-secret",
            "DOSSIERAGENT_OPENAI_BASE_URL": "https://openai.test/v1",
            "DOSSIERAGENT_ANTHROPIC_API_KEY": "anthropic-secret",
            "DOSSIERAGENT_ANTHROPIC_BASE_URL": "https://anthropic.test/v1",
            "DOSSIERAGENT_GOOGLE_API_KEY": "google-secret",
            "DOSSIERAGENT_GOOGLE_BASE_URL": "https://google.test/v1beta",
        }
        with (
            patch.dict("os.environ", env, clear=False),
            patch("dossieragent_core.ai.urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            response = self.client.get("/api/v1/ai/providers")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        providers = {provider["id"]: provider for provider in payload["providers"]}
        self.assertEqual(providers["openai"]["models"][0]["id"], "gpt-live")
        self.assertEqual(providers["anthropic"]["models"][0]["id"], "claude-live")
        self.assertEqual(providers["google"]["models"][0]["id"], "gemini-live")
        serialized = json.dumps(payload)
        self.assertNotIn("openai-secret", serialized)
        self.assertNotIn("anthropic-secret", serialized)
        self.assertNotIn("google-secret", serialized)

    def test_ai_provider_settings_store_secrets_encrypted_and_redacted(self) -> None:
        captured_authorization: list[str | None] = []

        def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
            captured_authorization.append(request.get_header("Authorization"))  # type: ignore[attr-defined]
            return FakeJsonResponse({"data": [{"id": "gpt-stored", "owned_by": "openai"}]})

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            env = {
                "DOSSIERAGENT_STORAGE_PATH": str(tmp_path / "storage"),
                "DOSSIERAGENT_OPENAI_API_KEY": "",
                "DOSSIERAGENT_ANTHROPIC_API_KEY": "",
                "DOSSIERAGENT_GOOGLE_API_KEY": "",
                "DOSSIERAGENT_CODEX_PROVIDER_PATH": "",
                "DOSSIERAGENT_OPENAI_BASE_URL": "https://openai.test/v1",
            }
            with (
                patch.dict("os.environ", env, clear=False),
                patch("dossieragent_core.ai.urllib.request.urlopen", side_effect=fake_urlopen),
            ):
                save_response = self.client.patch(
                    "/api/v1/ai/provider-settings/openai",
                    json={"api_key": "stored-openai-secret"},
                )
                settings_response = self.client.get("/api/v1/ai/provider-settings")
                providers_response = self.client.get("/api/v1/ai/providers")
                clear_response = self.client.patch(
                    "/api/v1/ai/provider-settings/openai",
                    json={"clear_fields": ["api_key"]},
                )
                secret_file = tmp_path / "storage" / "secrets" / "ai-provider-secrets.json.enc"
                key_file = tmp_path / "storage" / "secrets" / "master.key"
                secret_bytes = secret_file.read_bytes()
                secret_mode = secret_file.stat().st_mode & 0o777
                key_mode = key_file.stat().st_mode & 0o777

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(settings_response.status_code, 200)
        self.assertEqual(providers_response.status_code, 200)
        self.assertEqual(clear_response.status_code, 200)
        saved_openai = {
            provider["id"]: provider for provider in save_response.json()["providers"]
        }["openai"]
        cleared_openai = {
            provider["id"]: provider for provider in clear_response.json()["providers"]
        }["openai"]
        self.assertEqual(saved_openai["stored_fields"], ["api_key"])
        self.assertEqual(cleared_openai["stored_fields"], [])
        self.assertEqual(saved_openai["status"]["models"][0]["id"], "gpt-stored")
        self.assertEqual(captured_authorization, ["Bearer stored-openai-secret"] * 3)
        self.assertNotIn(b"stored-openai-secret", secret_bytes)
        self.assertEqual(secret_mode, 0o600)
        self.assertEqual(key_mode, 0o600)
        self.assertNotIn("stored-openai-secret", json.dumps(settings_response.json()))
        self.assertNotIn("stored-openai-secret", json.dumps(providers_response.json()))

    def test_ai_provider_environment_secret_overrides_stored_secret(self) -> None:
        captured_authorization: list[str | None] = []

        def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
            captured_authorization.append(request.get_header("Authorization"))  # type: ignore[attr-defined]
            return FakeJsonResponse({"data": [{"id": "gpt-env", "owned_by": "openai"}]})

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            env = {
                "DOSSIERAGENT_STORAGE_PATH": str(tmp_path / "storage"),
                "DOSSIERAGENT_OPENAI_API_KEY": "",
                "DOSSIERAGENT_OPENAI_BASE_URL": "https://openai.test/v1",
            }
            with patch.dict("os.environ", env, clear=False):
                self.client.patch(
                    "/api/v1/ai/provider-settings/openai",
                    json={"api_key": "stored-openai-secret"},
                )
            env["DOSSIERAGENT_OPENAI_API_KEY"] = "env-openai-secret"
            with (
                patch.dict("os.environ", env, clear=False),
                patch("dossieragent_core.ai.urllib.request.urlopen", side_effect=fake_urlopen),
            ):
                response = self.client.get("/api/v1/ai/providers")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["providers"][0]["models"][0]["id"], "gpt-env")
        self.assertEqual(captured_authorization, ["Bearer env-openai-secret"])
        self.assertNotIn("env-openai-secret", json.dumps(response.json()))

    def test_ai_chat_routes_tool_command_through_supervised_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}):
                response = self.client.post(
                    "/api/v1/ai/chat",
                    json={
                        "provider": "openai",
                        "model": "gpt-live",
                        "messages": [
                            {"role": "user", "content": "Affiche les annonces recommandees"}
                        ],
                    },
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "dossieragent_tools")
        self.assertEqual(payload["tool_call"]["status"], "accepted")
        self.assertEqual(payload["tool_call"]["result"]["type"], "listing_collection")
        self.assertIn("annonces trouvees", payload["message"]["content"])

    def test_ai_chat_blocks_external_contact_before_provider_call(self) -> None:
        with patch("dossieragent_core.ai.urllib.request.urlopen") as urlopen:
            response = self.client.post(
                "/api/v1/ai/chat",
                json={
                    "provider": "openai",
                    "model": "gpt-live",
                    "messages": [
                        {"role": "user", "content": "Envoie un email au proprietaire"}
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "dossieragent_tools")
        self.assertEqual(payload["tool_call"]["status"], "rejected")
        self.assertEqual(payload["tool_call"]["intent"], "blocked_external_contact")
        self.assertFalse(urlopen.called)

    def test_ai_chat_calls_provider_when_no_tool_intent_matches(self) -> None:
        captured_requests = []

        def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
            captured_requests.append((request, timeout))
            return FakeJsonResponse(
                {
                    "choices": [
                        {"message": {"role": "assistant", "content": "Bonjour depuis OpenAI."}}
                    ],
                    "usage": {"total_tokens": 12},
                }
            )

        with (
            patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_OPENAI_API_KEY": "openai-secret",
                    "DOSSIERAGENT_OPENAI_BASE_URL": "https://openai.test/v1",
                },
            ),
            patch("dossieragent_core.ai.urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            response = self.client.post(
                "/api/v1/ai/chat",
                json={
                    "provider": "openai",
                    "model": "gpt-live",
                    "messages": [{"role": "user", "content": "Bonjour"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["message"]["content"], "Bonjour depuis OpenAI.")
        self.assertIsNone(payload["tool_call"])
        request, _timeout = captured_requests[0]
        self.assertEqual(request.full_url, "https://openai.test/v1/chat/completions")  # type: ignore[attr-defined]
        self.assertNotIn("openai-secret", json.dumps(payload))

    def test_agent_command_can_return_plan_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
                initial_watch_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM market_watches"
                ).fetchone()["count"]
            finally:
                connection.close()

            with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}):
                response = self.client.post(
                    "/api/v1/agent/commands",
                    json={
                        "message": "Cree une veille pour Lyon budget 900 T2",
                        "execute": False,
                    },
                )

            connection = create_connection(database_path)
            try:
                final_watch_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM market_watches"
                ).fetchone()["count"]
            finally:
                connection.close()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["intent"], "create_market_watch")
        self.assertEqual(payload["result"]["type"], "command_plan")
        self.assertTrue(payload["result"]["requires_confirmation"])
        self.assertEqual(payload["result"]["parameters"]["city"], "Lyon")
        self.assertEqual(final_watch_count, initial_watch_count)

    def test_agent_command_runs_market_watch_through_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}):
                response = self.client.post(
                    "/api/v1/agent/commands",
                    json={"command": "Lance un scan de la veille watch_toulouse_t2"},
                )
                run_id = response.json()["result"]["run"]["id"]
                run_detail = self.client.get(f"/api/v1/agent-runs/{run_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["intent"], "run_market_watch")
        self.assertEqual(payload["result"]["type"], "agent_run")
        self.assertEqual(payload["result"]["run"]["trigger_type"], "command")
        self.assertEqual(run_detail.status_code, 200)
        self.assertEqual(run_detail.json()["current_step"], "completed")

    def test_agent_command_analyzes_dossier_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                response = self.client.post(
                    "/api/v1/agent/commands",
                    json={"command": "Analyse mon dossier"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["intent"], "analyze_dossier")
        self.assertEqual(payload["result"]["type"], "dossier_snapshot")
        self.assertEqual(payload["result"]["snapshot"]["readiness_score"], 78)
        self.assertEqual(
            payload["result"]["snapshot"]["missing_docs"],
            ["employment_contract", "latest_tax_notice"],
        )

    def test_agent_command_creates_market_watch_from_structured_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}):
                response = self.client.post(
                    "/api/v1/agent/commands",
                    json={"command": "Cree une veille pour Lyon budget 900 T2"},
                )
                watches = self.client.get("/api/v1/market-watches")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["intent"], "create_market_watch")
        self.assertEqual(payload["result"]["type"], "market_watch")
        self.assertEqual(payload["result"]["criteria"]["cities"], ["Lyon"])
        self.assertEqual(payload["result"]["criteria"]["budget_max"], 900.0)
        self.assertEqual(payload["result"]["criteria"]["rooms_min"], 2.0)
        self.assertEqual(payload["result"]["watch"]["status"], "active")
        self.assertEqual(payload["result"]["watch"]["source_config"], {"sources": ["manual_urls"]})
        self.assertIn(payload["result"]["watch"]["id"], {item["id"] for item in watches.json()["items"]})

    def test_cron_route_requires_secret_and_runs_due_watches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
                connection.execute(
                    """
                    UPDATE market_watches
                    SET next_run_at = ?
                    WHERE id = ?
                    """,
                    ("2000-01-01T00:00:00Z", "watch_toulouse_t2"),
                )
                connection.commit()
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_CRON_SECRET": "cron-test-secret",
                },
            ):
                missing_secret = self.client.post("/api/v1/internal/cron/run-due-watches")
                authorized = self.client.post(
                    "/api/v1/internal/cron/run-due-watches",
                    headers={"Authorization": "Bearer cron-test-secret"},
                )
                run_id = authorized.json()["runs"][0]["run_id"]
                run_detail = self.client.get(f"/api/v1/agent-runs/{run_id}")
                run_events = self.client.get(f"/api/v1/agent-runs/{run_id}/events")
                watches = self.client.get("/api/v1/market-watches")

        self.assertEqual(missing_secret.status_code, 403)
        self.assertEqual(missing_secret.json()["error"]["code"], "cron_secret_required")
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.json()["guard"], "secret")
        self.assertEqual(authorized.json()["due_count"], 1)
        self.assertEqual(authorized.json()["started_count"], 1)
        self.assertEqual(authorized.json()["skipped_count"], 0)
        self.assertEqual(authorized.json()["runs"][0]["watch_id"], "watch_toulouse_t2")
        self.assertEqual(run_detail.status_code, 200)
        self.assertEqual(run_detail.json()["trigger_type"], "cron")
        self.assertEqual(run_detail.json()["current_step"], "completed")
        self.assertEqual(run_events.status_code, 200)
        self.assertEqual(
            [event["type"] for event in run_events.json()["items"]],
            [
                "run_accepted",
                "source_scan_started",
                "source_scan_finished",
                "normalized",
                "deduped",
                "ranked",
                "index_skipped",
                "notifications_created",
                "completed",
            ],
        )
        self.assertEqual(watches.status_code, 200)
        toulouse_watch = next(
            item for item in watches.json()["items"] if item["id"] == "watch_toulouse_t2"
        )
        self.assertNotEqual(toulouse_watch["next_run_at"], "2000-01-01T00:00:00Z")
        self.assertIsNotNone(toulouse_watch["last_run_at"])

    def test_listing_search_detail_and_decision_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
            finally:
                connection.close()

            with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": str(database_path)}):
                recommended = self.client.get(
                    "/api/v1/listings",
                    params={"status": "recommended", "limit": 2},
                )
                filtered = self.client.get(
                    "/api/v1/listings",
                    params={"city": "Toulouse", "district": "Carmes", "min_score": 80},
                )
                listing_detail = self.client.get("/api/v1/listings/lst_001")
                patch_listing = self.client.patch(
                    "/api/v1/listings/lst_001",
                    json={"status": "saved"},
                )
                patched_detail = self.client.get("/api/v1/listings/lst_001")
                invalid_patch = self.client.patch(
                    "/api/v1/listings/lst_001",
                    json={"status": "emailed"},
                )

        self.assertEqual(recommended.status_code, 200)
        recommended_payload = recommended.json()
        self.assertEqual(recommended_payload["source"], "sqlite")
        self.assertEqual(recommended_payload["total"], 4)
        self.assertEqual(len(recommended_payload["items"]), 2)
        self.assertEqual(recommended_payload["next_cursor"], "2")
        self.assertEqual(recommended_payload["items"][0]["id"], "lst_001")
        self.assertEqual(recommended_payload["items"][0]["risk_flags"], ["charges_non_detaillees"])
        self.assertEqual(
            recommended_payload["items"][0]["image_urls"],
            [
                "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=900&q=80"
            ],
        )
        self.assertEqual(
            recommended_payload["items"][0]["source_url"],
            "https://demo.dossieragent.local/listings/001",
        )

        self.assertEqual(filtered.status_code, 200)
        self.assertEqual([item["id"] for item in filtered.json()["items"]], ["lst_002"])

        self.assertEqual(listing_detail.status_code, 200)
        detail_payload = listing_detail.json()
        self.assertEqual(detail_payload["id"], "lst_001")
        self.assertEqual(detail_payload["source_url"], "https://demo.dossieragent.local/listings/001")
        self.assertEqual(
            detail_payload["image_urls"],
            [
                "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=900&q=80"
            ],
        )
        self.assertIn("Sous le budget maximum", detail_payload["explanation"])

        self.assertEqual(patch_listing.status_code, 200)
        self.assertEqual(patch_listing.json()["status"], "saved")
        self.assertEqual(patched_detail.json()["status"], "saved")
        self.assertEqual(invalid_patch.status_code, 400)
        self.assertEqual(invalid_patch.json()["error"]["code"], "invalid_listing_status")

    def test_listing_import_url_creates_listing_from_browser_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                    "DOSSIERAGENT_BROWSER_INTERNAL_SECRET": "",
                    "DOSSIERAGENT_ELASTIC_URL": "",
                },
            ):
                response = self.client.post(
                    "/api/v1/listings/import-url",
                    json={
                        "url": "https://demo.example/listings/imported-t2?utm=1",
                        "source": "demo_seed",
                        "watch_id": "watch_toulouse_t2",
                        "html": LISTING_IMPORT_HTML,
                    },
                )

            connection = create_connection(database_path)
            try:
                row = connection.execute(
                    "SELECT * FROM listings WHERE source_listing_id = ?",
                    ("imported-t2",),
                ).fetchone()
            finally:
                connection.close()

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["action"], "created")
        self.assertEqual(payload["browser"]["status"], "succeeded")
        self.assertEqual(payload["search_index"]["reason"], "elastic_not_configured")
        listing = payload["listing"]
        self.assertEqual(listing["title"], "T2 Import Carmes proche metro")
        self.assertEqual(listing["canonical_url"], "https://demo.example/listings/imported-t2")
        self.assertEqual(listing["source_listing_id"], "imported-t2")
        self.assertEqual(listing["city"], "Toulouse")
        self.assertEqual(listing["district"], "Carmes")
        self.assertEqual(
            listing["image_urls"],
            ["https://cdn.demo.example/listings/imported-t2.jpg"],
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], listing["id"])

    def test_listing_import_url_updates_duplicate_canonical_listing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            env = {
                "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                "DOSSIERAGENT_BROWSER_INTERNAL_SECRET": "",
                "DOSSIERAGENT_ELASTIC_URL": "",
            }
            payload = {
                "url": "https://demo.example/listings/imported-t2?utm=1",
                "source": "demo_seed",
                "watch_id": "watch_toulouse_t2",
                "html": LISTING_IMPORT_HTML,
            }
            with patch.dict("os.environ", env):
                first_response = self.client.post("/api/v1/listings/import-url", json=payload)
                second_response = self.client.post("/api/v1/listings/import-url", json=payload)

            listing_id = first_response.json()["listing"]["id"]
            connection = create_connection(database_path)
            try:
                duplicate_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM listings WHERE canonical_url = ?",
                    ("https://demo.example/listings/imported-t2",),
                ).fetchone()["count"]
            finally:
                connection.close()

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(first_response.json()["action"], "created")
        self.assertEqual(second_response.json()["action"], "updated")
        self.assertEqual(second_response.json()["listing"]["id"], listing_id)
        self.assertEqual(duplicate_count, 1)

    def test_listing_import_url_rejects_unsupported_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                    "DOSSIERAGENT_BROWSER_INTERNAL_SECRET": "",
                },
            ):
                response = self.client.post(
                    "/api/v1/listings/import-url",
                    json={
                        "url": "javascript:alert(1)",
                        "source": "manual_url",
                        "watch_id": "watch_toulouse_t2",
                        "html": LISTING_IMPORT_HTML,
                    },
                )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "listing_extraction_failed")

    def test_internal_browser_extract_is_guarded_and_returns_candidate(self) -> None:
        with patch.dict("os.environ", {"DOSSIERAGENT_BROWSER_INTERNAL_SECRET": "browser-secret"}):
            forbidden_response = self.client.post(
                "/api/v1/internal/browser/extract",
                json={
                    "url": "https://demo.example/listings/imported-t2",
                    "source": "demo_seed",
                    "html": LISTING_IMPORT_HTML,
                },
            )
            authorized_response = self.client.post(
                "/api/v1/internal/browser/extract",
                headers={"Authorization": "Bearer browser-secret"},
                json={
                    "url": "https://demo.example/listings/imported-t2",
                    "source": "demo_seed",
                    "html": LISTING_IMPORT_HTML,
                },
            )

        self.assertEqual(forbidden_response.status_code, 403)
        self.assertEqual(forbidden_response.json()["error"]["code"], "browser_internal_secret_required")
        self.assertEqual(authorized_response.status_code, 200)
        self.assertEqual(authorized_response.json()["guard"], "secret")
        self.assertEqual(authorized_response.json()["status"], "succeeded")
        self.assertEqual(
            authorized_response.json()["candidate"]["title"],
            "T2 Import Carmes proche metro",
        )

    def test_dossier_document_upload_extracts_pdf_and_stores_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                upload_response = self.client.post(
                    "/api/v1/dossier/documents",
                    files={
                        "file": (
                            "payslip_may.pdf",
                            build_pdf_bytes(
                                "Bulletin de paie mai 2026\n"
                                "Employeur DossierAgent SAS\n"
                                "Salaire net a payer 2450 EUR"
                            ),
                            "application/pdf",
                        )
                    },
                    data={"declared_type": "payslip", "owner_type": "user"},
                )
                document_id = upload_response.json()["document_id"]
                detail_response = self.client.get(f"/api/v1/dossier/documents/{document_id}")
                list_response = self.client.get("/api/v1/dossier/documents")

            connection = create_connection(database_path)
            try:
                row = connection.execute(
                    "SELECT * FROM dossier_documents WHERE id = ?",
                    (document_id,),
                ).fetchone()
                extracted_text_path = Path(row["extracted_text_path"])
                extracted_text_exists = extracted_text_path.exists()
                extracted_text = extracted_text_path.read_text(encoding="utf-8")
            finally:
                connection.close()

        self.assertEqual(upload_response.status_code, 201)
        payload = upload_response.json()
        self.assertEqual(payload["status"], "uploaded")
        self.assertEqual(payload["analysis_status"], "queued")
        self.assertEqual(payload["filename"], "payslip_may.pdf")
        self.assertEqual(payload["detected_type"], "payslip")
        self.assertEqual(payload["page_count"], 1)
        self.assertTrue(payload["has_extracted_text"])
        self.assertNotIn("storage_path", payload)
        self.assertNotIn("extracted_text_path", payload)

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["document_id"], document_id)
        self.assertEqual(list_response.status_code, 200)
        self.assertIn(document_id, {item["document_id"] for item in list_response.json()["items"]})
        self.assertIsNotNone(row["extracted_text_path"])
        self.assertTrue(extracted_text_exists)
        self.assertIn("Bulletin de paie", extracted_text)

    def test_dossier_document_preview_and_delete_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                upload_response = self.client.post(
                    "/api/v1/dossier/documents",
                    files={
                        "file": (
                            "preview.pdf",
                            build_pdf_bytes("Document a previsualiser"),
                            "application/pdf",
                        )
                    },
                    data={"declared_type": "other", "owner_type": "user"},
                )
                document_id = upload_response.json()["document_id"]
                preview_response = self.client.get(f"/api/v1/dossier/documents/{document_id}/preview")
                cross_user_preview_response = self.client.get(
                    f"/api/v1/dossier/documents/{document_id}/preview",
                    headers={"X-Demo-User-Id": "usr_other"},
                )
                delete_response = self.client.delete(f"/api/v1/dossier/documents/{document_id}")
                list_response = self.client.get("/api/v1/dossier/documents")
                preview_deleted_response = self.client.get(
                    f"/api/v1/dossier/documents/{document_id}/preview"
                )

        self.assertEqual(upload_response.status_code, 201)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_response.headers["content-type"], "application/pdf")
        self.assertIn("inline", preview_response.headers["content-disposition"])
        self.assertTrue(preview_response.content.startswith(b"%PDF"))
        self.assertEqual(cross_user_preview_response.status_code, 404)
        self.assertEqual(cross_user_preview_response.json()["error"]["code"], "document_not_found")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["status"], "deleted")
        self.assertNotIn(document_id, {item["document_id"] for item in list_response.json()["items"]})
        self.assertEqual(preview_deleted_response.status_code, 404)
        self.assertEqual(preview_deleted_response.json()["error"]["code"], "document_not_found")

    def test_dossier_document_delete_recomputes_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                initial_readiness = self.client.get("/api/v1/dossier/readiness")
                delete_response = self.client.delete("/api/v1/dossier/documents/doc_identity")
                list_response = self.client.get("/api/v1/dossier/documents")
                updated_readiness = self.client.get("/api/v1/dossier/readiness")

        self.assertEqual(initial_readiness.status_code, 200)
        self.assertNotIn("identity", initial_readiness.json()["missing_docs"])
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["status"], "deleted")
        self.assertNotIn(
            "doc_identity",
            {document["document_id"] for document in list_response.json()["items"]},
        )
        self.assertIn("identity", updated_readiness.json()["missing_docs"])
        self.assertNotIn("doc_identity", updated_readiness.json()["valid_docs"])

    def test_bad_dossier_upload_is_marked_needs_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                response = self.client.post(
                    "/api/v1/dossier/documents",
                    files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
                    data={"declared_type": "payslip", "owner_type": "user"},
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], "needs_review")
        self.assertFalse(payload["has_extracted_text"])
        self.assertTrue(payload["issues"][0].startswith("pdf_open_failed"))

    def test_dossier_readiness_gets_latest_snapshot_and_analyzes_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                initial_response = self.client.get("/api/v1/dossier/readiness")
                analyze_response = self.client.post("/api/v1/dossier/analyze")
                latest_response = self.client.get("/api/v1/dossier/readiness")

        self.assertEqual(initial_response.status_code, 200)
        initial_payload = initial_response.json()
        self.assertEqual(initial_payload["readiness_score"], 78)
        self.assertEqual(initial_payload["missing_docs"], ["employment_contract", "latest_tax_notice"])
        self.assertIn("Avis d impot possiblement obsolete.", initial_payload["warnings"])

        self.assertEqual(analyze_response.status_code, 201)
        analyzed_payload = analyze_response.json()
        self.assertEqual(analyzed_payload["readiness_score"], 78)
        self.assertTrue(analyzed_payload["can_contact"])
        self.assertFalse(analyzed_payload["can_send_full_dossier"])
        self.assertEqual(analyzed_payload["missing_docs"], ["employment_contract", "latest_tax_notice"])
        self.assertEqual(latest_response.json()["snapshot_id"], analyzed_payload["snapshot_id"])

    def test_contact_packet_creation_creates_pending_user_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                response = self.client.post(
                    "/api/v1/contact-packets",
                    json={
                        "listing_id": "lst_001",
                        "language": "fr",
                        "tone": "polite_direct",
                        "include_dossier_summary": True,
                    },
                )

            packet_id = response.json()["id"]
            user_check_id = response.json()["user_check_id"]
            connection = create_connection(database_path)
            try:
                packet_row = connection.execute(
                    "SELECT * FROM contact_packets WHERE id = ?",
                    (packet_id,),
                ).fetchone()
                check_row = connection.execute(
                    "SELECT * FROM user_checks WHERE id = ?",
                    (user_check_id,),
                ).fetchone()
            finally:
                connection.close()

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], "ready_for_review")
        self.assertEqual(payload["listing_id"], "lst_001")
        self.assertIn("T2 Saint-Cyprien", payload["message_draft"])
        self.assertTrue(payload["questions_to_ask"])
        self.assertEqual(payload["dossier_summary"]["missing_documents"], ["employment_contract", "latest_tax_notice"])
        self.assertFalse(payload["dossier_summary"]["can_send_full_dossier"])
        self.assertEqual(packet_row["status"], "ready_for_review")
        self.assertEqual(check_row["status"], "pending")
        self.assertEqual(check_row["resource_type"], "contact_packet")
        self.assertEqual(check_row["resource_id"], packet_id)

    def test_contact_packet_list_detail_edit_and_mark_used_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                list_response = self.client.get("/api/v1/contact-packets")
                packet_id = list_response.json()["items"][0]["id"]
                detail_response = self.client.get(f"/api/v1/contact-packets/{packet_id}")
                patch_response = self.client.patch(
                    f"/api/v1/contact-packets/{packet_id}",
                    json={
                        "status": "approved",
                        "message_draft": "Message relu et pret a copier.",
                        "questions_to_ask": ["Le logement est-il toujours disponible ?"],
                    },
                )
                invalid_patch_response = self.client.patch(
                    f"/api/v1/contact-packets/{packet_id}",
                    json={"status": "emailed"},
                )
                mark_used_response = self.client.post(
                    f"/api/v1/contact-packets/{packet_id}/mark-used",
                    json={"channel": "manual_copy"},
                )

        self.assertEqual(list_response.status_code, 200)
        self.assertGreaterEqual(len(list_response.json()["items"]), 1)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["id"], packet_id)
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.json()["status"], "approved")
        self.assertEqual(patch_response.json()["message_draft"], "Message relu et pret a copier.")
        self.assertEqual(
            patch_response.json()["questions_to_ask"],
            ["Le logement est-il toujours disponible ?"],
        )
        self.assertEqual(invalid_patch_response.status_code, 400)
        self.assertEqual(
            invalid_patch_response.json()["error"]["code"],
            "invalid_contact_packet_status",
        )
        self.assertEqual(mark_used_response.status_code, 200)
        self.assertEqual(mark_used_response.json()["status"], "used")
        self.assertEqual(mark_used_response.json()["used_channel"], "manual_copy")
        self.assertIsNotNone(mark_used_response.json()["used_at"])

    def test_contact_packet_creation_respects_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                first_response = self.client.post(
                    "/api/v1/contact-packets",
                    headers={"Idempotency-Key": "packet-key"},
                    json={
                        "listing_id": "lst_001",
                        "language": "fr",
                        "tone": "polite_direct",
                        "include_dossier_summary": True,
                    },
                )
                replay_response = self.client.post(
                    "/api/v1/contact-packets",
                    headers={"Idempotency-Key": "packet-key"},
                    json={
                        "listing_id": "lst_001",
                        "language": "fr",
                        "tone": "polite_direct",
                        "include_dossier_summary": True,
                    },
                )
                conflicting_payload_response = self.client.post(
                    "/api/v1/contact-packets",
                    headers={"Idempotency-Key": "packet-key"},
                    json={
                        "listing_id": "lst_002",
                        "language": "en",
                        "tone": "warm",
                        "include_dossier_summary": False,
                    },
                )

            created_packet_id = first_response.json()["id"]
            connection = create_connection(database_path)
            try:
                packet_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM contact_packets WHERE id = ?",
                    (created_packet_id,),
                ).fetchone()["count"]
                check_count = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM user_checks
                    WHERE resource_type = 'contact_packet' AND resource_id = ?
                    """,
                    (created_packet_id,),
                ).fetchone()["count"]
            finally:
                connection.close()

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(replay_response.status_code, 201)
        self.assertEqual(conflicting_payload_response.status_code, 201)
        self.assertEqual(replay_response.json()["id"], first_response.json()["id"])
        self.assertEqual(replay_response.json()["user_check_id"], first_response.json()["user_check_id"])
        self.assertEqual(conflicting_payload_response.json()["id"], first_response.json()["id"])
        self.assertEqual(conflicting_payload_response.json()["listing_id"], "lst_001")
        self.assertEqual(packet_count, 1)
        self.assertEqual(check_count, 1)

    def test_user_checks_and_notifications_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                checks_response = self.client.get("/api/v1/user-checks")
                check_id = checks_response.json()["items"][0]["id"]
                complete_response = self.client.post(
                    f"/api/v1/user-checks/{check_id}/complete",
                    json={"decision": "approved", "note": "Message correct."},
                )
                completed_checks_response = self.client.get("/api/v1/user-checks")

                notifications_response = self.client.get("/api/v1/notifications")
                unread_response = self.client.get("/api/v1/notifications?unread_only=true")
                notification_id = notifications_response.json()["items"][0]["id"]
                read_response = self.client.post(f"/api/v1/notifications/{notification_id}/read")
                unread_after_response = self.client.get("/api/v1/notifications?unread_only=true")

        self.assertEqual(checks_response.status_code, 200)
        self.assertEqual(len(checks_response.json()["items"]), 3)
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.json()["status"], "completed")
        self.assertEqual(complete_response.json()["completed_with"], "approved")
        self.assertEqual(len(completed_checks_response.json()["items"]), 2)

        self.assertEqual(notifications_response.status_code, 200)
        self.assertEqual(len(notifications_response.json()["items"]), 5)
        self.assertEqual(len(unread_response.json()["items"]), 5)
        self.assertEqual(read_response.status_code, 200)
        self.assertIsNotNone(read_response.json()["read_at"])
        self.assertEqual(len(unread_after_response.json()["items"]), 4)

    def test_user_check_completion_respects_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            database_path = tmp_path / "dossieragent.db"
            storage_path = tmp_path / "storage"
            connection = create_connection(database_path)
            try:
                seed_demo_data(connection, storage_path=storage_path)
            finally:
                connection.close()

            with patch.dict(
                "os.environ",
                {
                    "DOSSIERAGENT_SQLITE_PATH": str(database_path),
                    "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
                },
            ):
                checks_response = self.client.get("/api/v1/user-checks")
                check_ids = [item["id"] for item in checks_response.json()["items"]]
                first_response = self.client.post(
                    f"/api/v1/user-checks/{check_ids[0]}/complete",
                    headers={"Idempotency-Key": "check-key"},
                    json={"decision": "approved", "note": "OK."},
                )
                replay_response = self.client.post(
                    f"/api/v1/user-checks/{check_ids[0]}/complete",
                    headers={"Idempotency-Key": "check-key"},
                    json={"decision": "rejected", "note": "Different duplicate payload."},
                )
                same_check_without_key_response = self.client.post(
                    f"/api/v1/user-checks/{check_ids[0]}/complete",
                    json={"decision": "approved", "note": "Already done."},
                )
                conflicting_check_response = self.client.post(
                    f"/api/v1/user-checks/{check_ids[1]}/complete",
                    headers={"Idempotency-Key": "check-key"},
                    json={"decision": "approved", "note": "Wrong resource."},
                )

            connection = create_connection(database_path)
            try:
                completed_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM user_checks WHERE status = 'completed'"
                ).fetchone()["count"]
            finally:
                connection.close()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["status"], "completed")
        self.assertEqual(first_response.json()["completed_with"], "approved")
        self.assertEqual(replay_response.status_code, 200)
        self.assertEqual(replay_response.json(), first_response.json())
        self.assertEqual(same_check_without_key_response.status_code, 409)
        self.assertEqual(
            same_check_without_key_response.json()["error"]["code"],
            "user_check_already_completed",
        )
        self.assertEqual(conflicting_check_response.status_code, 409)
        self.assertEqual(conflicting_check_response.json()["error"]["code"], "idempotency_key_conflict")
        self.assertEqual(completed_count, 1)


def build_pdf_bytes(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    try:
        return document.tobytes()
    finally:
        document.close()


class FakeAuthClient:
    def __init__(self, *, authenticated_user: AuthenticatedUser | None = None) -> None:
        self.authenticated_user = authenticated_user or demo_auth_user(email="demo@example.com")
        self.register_payload: dict[str, str | None] = {}
        self.recover_payload: dict[str, str | None] = {}
        self.logout_token: str | None = None

    def login(self, *, email: str, password: str) -> AuthSession:
        self._assert_password(password)
        return AuthSession(
            access_token="access_token_123",
            refresh_token="refresh_token_123",
            token_type="bearer",
            expires_in=3600,
            expires_at=1893456000,
            user=auth_user_with_email(self.authenticated_user, email),
        )

    def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
        redirect_to: str | None = None,
    ) -> AuthSignupResult:
        self._assert_password(password)
        self.register_payload = {
            "email": email,
            "display_name": display_name,
            "redirect_to": redirect_to,
        }
        session = AuthSession(
            access_token="access_token_registered",
            refresh_token="refresh_token_registered",
            token_type="bearer",
            expires_in=3600,
            expires_at=1893456000,
            user=auth_user_with_email(self.authenticated_user, email),
        )
        return AuthSignupResult(status="session_created", user=session.user, session=session)

    def refresh(self, *, refresh_token: str) -> AuthSession:
        self._assert_refresh_token(refresh_token)
        return AuthSession(
            access_token="access_token_refreshed",
            refresh_token="refresh_token_refreshed",
            token_type="bearer",
            expires_in=3600,
            expires_at=1893459600,
            user=self.authenticated_user,
        )

    def get_user(self, *, access_token: str) -> AuthenticatedUser:
        if access_token != "access_token_123":
            raise AssertionError(f"Unexpected access token: {access_token}")
        return self.authenticated_user

    def recover_password(self, *, email: str, redirect_to: str | None = None) -> None:
        self.recover_payload = {"email": email, "redirect_to": redirect_to}

    def logout(self, *, access_token: str) -> None:
        self.logout_token = access_token

    def _assert_password(self, password: str) -> None:
        if password != "correct-password":
            raise AssertionError("Unexpected password.")

    def _assert_refresh_token(self, refresh_token: str) -> None:
        if refresh_token != "refresh_token_123":
            raise AssertionError("Unexpected refresh token.")


def demo_auth_user(*, email: str) -> AuthenticatedUser:
    return supabase_auth_user(
        email=email,
        provider_user_id="supabase_user_123",
        app_user_id="usr_demo",
        metadata_app_user_id="usr_demo",
    )


def auth_user_with_email(auth_user: AuthenticatedUser, email: str) -> AuthenticatedUser:
    user_metadata = auth_user.raw_user.get("user_metadata")
    metadata_app_user_id = None
    if isinstance(user_metadata, dict):
        metadata_app_user_id = user_metadata.get("dossieragent_user_id")
    return supabase_auth_user(
        email=email,
        provider_user_id=auth_user.provider_user_id,
        app_user_id=auth_user.app_user_id,
        metadata_app_user_id=metadata_app_user_id if isinstance(metadata_app_user_id, str) else None,
    )


def supabase_auth_user(
    *,
    email: str,
    provider_user_id: str,
    app_user_id: str,
    metadata_app_user_id: str | None = None,
) -> AuthenticatedUser:
    user_metadata = {"dossieragent_user_id": metadata_app_user_id} if metadata_app_user_id else {}
    return AuthenticatedUser(
        provider="supabase",
        provider_user_id=provider_user_id,
        app_user_id=app_user_id,
        email=email,
        display_name="Demo User",
        raw_user={
            "id": provider_user_id,
            "email": email,
            "user_metadata": user_metadata,
        },
    )


class FakeUrlopenResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeUrlopenResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()

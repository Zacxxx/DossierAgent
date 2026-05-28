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
        self.assertEqual(payload["dossier"]["missing_docs"], ["employment_contract", "latest_tax_notice"])
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
                conflicting_run = self.client.post(
                    "/api/v1/market-watches/watch_toulouse_t2/run-now",
                    headers={"Idempotency-Key": "different-key"},
                )
                run_id = first_run.json()["run_id"]
                run_detail = self.client.get(f"/api/v1/agent-runs/{run_id}")
                run_events = self.client.get(f"/api/v1/agent-runs/{run_id}/events")

        self.assertEqual(first_run.status_code, 202)
        self.assertEqual(first_run.json()["status"], "running")
        self.assertFalse(first_run.json()["idempotent_replay"])
        self.assertEqual(replayed_run.status_code, 202)
        self.assertEqual(replayed_run.json()["run_id"], first_run.json()["run_id"])
        self.assertTrue(replayed_run.json()["idempotent_replay"])
        self.assertEqual(conflicting_run.status_code, 409)
        self.assertEqual(conflicting_run.json()["error"]["code"], "run_already_active")
        self.assertEqual(run_detail.status_code, 200)
        self.assertEqual(run_detail.json()["id"], run_id)
        self.assertEqual(run_detail.json()["current_step"], "accepted")
        self.assertEqual(run_events.status_code, 200)
        self.assertEqual(
            [event["type"] for event in run_events.json()["items"]],
            ["run_accepted", "worker_pending"],
        )

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
        self.assertEqual(run_detail.json()["current_step"], "accepted")
        self.assertEqual(run_events.status_code, 200)
        self.assertEqual(
            [event["type"] for event in run_events.json()["items"]],
            ["run_accepted", "worker_pending"],
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

        self.assertEqual(filtered.status_code, 200)
        self.assertEqual([item["id"] for item in filtered.json()["items"]], ["lst_002"])

        self.assertEqual(listing_detail.status_code, 200)
        detail_payload = listing_detail.json()
        self.assertEqual(detail_payload["id"], "lst_001")
        self.assertEqual(detail_payload["source_url"], "https://demo.dossieragent.local/listings/001")
        self.assertIn("Sous le budget maximum", detail_payload["explanation"])

        self.assertEqual(patch_listing.status_code, 200)
        self.assertEqual(patch_listing.json()["status"], "saved")
        self.assertEqual(patched_detail.json()["status"], "saved")
        self.assertEqual(invalid_patch.status_code, 400)
        self.assertEqual(invalid_patch.json()["error"]["code"], "invalid_listing_status")

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


def build_pdf_bytes(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    try:
        return document.tobytes()
    finally:
        document.close()


if __name__ == "__main__":
    unittest.main()

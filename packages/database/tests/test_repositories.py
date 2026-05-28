from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dossieragent_database import build_repositories, create_connection, run_migrations
from dossieragent_database.seed import seed_demo_data


class RepositoryTests(unittest.TestCase):
    def test_repositories_cover_create_read_update_and_dashboard_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = create_connection(Path(tmp_dir) / "dossieragent.db")
            try:
                run_migrations(connection)
                repos = build_repositories(connection)
                now = "2026-05-27T16:00:00Z"

                user = repos.users.create(
                    {
                        "id": "usr_001",
                        "email": "demo@example.com",
                        "password_hash": "hash",
                        "display_name": "Demo User",
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                criteria = repos.search_criteria.create(
                    {
                        "id": "crit_001",
                        "user_id": user["id"],
                        "mode": "rent",
                        "cities_json": '["Toulouse"]',
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                watch = repos.market_watches.create(
                    {
                        "id": "watch_001",
                        "user_id": user["id"],
                        "criteria_id": criteria["id"],
                        "name": "Toulouse T2",
                        "status": "active",
                        "frequency": "twice_daily",
                        "next_run_at": "2026-05-27T18:30:00Z",
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                listing = repos.listings.create(
                    {
                        "id": "lst_001",
                        "user_id": user["id"],
                        "watch_id": watch["id"],
                        "source": "seed",
                        "source_url": "https://example.test/listings/1",
                        "canonical_url": "https://example.test/listings/1",
                        "canonical_url_hash": "hash_001",
                        "title": "T2 Saint Cyprien",
                        "city": "Toulouse",
                        "district": "Saint-Cyprien",
                        "surface": 39,
                        "composite_fingerprint": "fp_001",
                        "status": "new",
                        "first_seen_at": now,
                        "last_seen_at": now,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                run = repos.agent_runs.create(
                    {
                        "id": "run_001",
                        "user_id": user["id"],
                        "watch_id": watch["id"],
                        "trigger_type": "manual",
                        "intent": "run_market_watch",
                        "status": "running",
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                repos.agent_events.create(
                    {
                        "id": "evt_001",
                        "run_id": run["id"],
                        "user_id": user["id"],
                        "type": "run_started",
                        "severity": "info",
                        "message": "Run started",
                        "created_at": now,
                    }
                )
                repos.user_checks.create(
                    {
                        "id": "chk_001",
                        "user_id": user["id"],
                        "type": "packet_review",
                        "resource_type": "contact_packet",
                        "resource_id": "pkt_001",
                        "title": "Review packet",
                        "summary": "Packet needs review",
                        "status": "pending",
                        "created_at": now,
                    }
                )
                repos.notifications.create(
                    {
                        "id": "ntf_001",
                        "user_id": user["id"],
                        "type": "new_listing",
                        "title": "New listing",
                        "body": "A listing is ready",
                        "created_at": now,
                    }
                )
                repos.idempotency_keys.create(
                    {
                        "id": "idem_001",
                        "user_id": user["id"],
                        "scope": "run_now",
                        "idempotency_key": "test-key",
                        "resource_type": "agent_run",
                        "resource_id": run["id"],
                        "created_at": now,
                    }
                )
                document = repos.dossier_documents.create(
                    {
                        "id": "doc_001",
                        "user_id": user["id"],
                        "filename": "payslip.pdf",
                        "storage_path": "storage/documents/usr_001/doc_001/payslip.pdf",
                        "mime_type": "application/pdf",
                        "file_size": 2048,
                        "sha256": "sha256-doc-001",
                        "declared_type": "payslip",
                        "detected_type": "payslip",
                        "detected_owner_type": "user",
                        "page_count": 1,
                        "status": "uploaded",
                        "extracted_text_path": "storage/extracted_text/usr_001/doc_001.txt",
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                snapshot = repos.dossier_snapshots.create(
                    {
                        "id": "snap_001",
                        "user_id": user["id"],
                        "readiness_score": 70,
                        "can_contact": 1,
                        "can_send_full_dossier": 0,
                        "missing_documents_json": '[{"type":"employment_contract"}]',
                        "valid_documents_json": '["doc_001"]',
                        "warnings_json": '["Avis fiscal a verifier."]',
                        "recommendations_json": '["Ajouter le contrat de travail."]',
                        "created_at": now,
                    }
                )
                packet = repos.contact_packets.create(
                    {
                        "id": "pkt_001",
                        "user_id": user["id"],
                        "listing_id": listing["id"],
                        "language": "fr",
                        "tone": "polite_direct",
                        "status": "ready_for_review",
                        "message_draft": "Bonjour, je vous contacte au sujet du T2.",
                        "questions_json": '["Une visite est elle possible ?"]',
                        "dossier_summary_json": '{"can_contact":true}',
                        "created_at": now,
                        "updated_at": now,
                    }
                )

                updated_listing = repos.listings.update(listing["id"], {"status": "saved"})
                listing_search_rows, listing_search_total = repos.listings.search(
                    user_id=user["id"],
                    filters={"status": "saved", "q": "Cyprien", "min_surface": 1},
                    limit=10,
                    offset=0,
                )
                found_listing = repos.listings.find_for_user(
                    user_id=user["id"],
                    listing_id=listing["id"],
                )
                events = repos.agent_events.list_for_run(run["id"])
                counts = repos.dashboard.counts_for_user(user["id"])
                idempotency_key = repos.idempotency_keys.find_key(
                    user_id=user["id"],
                    scope="run_now",
                    idempotency_key="test-key",
                )
                found_document = repos.dossier_documents.find_for_user(
                    user_id=user["id"],
                    document_id=document["id"],
                )
                active_documents = repos.dossier_documents.list_active_for_user(user["id"])
                latest_snapshot = repos.dossier_snapshots.latest_for_user(user["id"])
                found_packet = repos.contact_packets.find_for_user(user_id=user["id"], packet_id=packet["id"])
                pending_checks = repos.user_checks.list_pending_for_user(user["id"])

                self.assertEqual(repos.users.get("usr_001")["email"], "demo@example.com")
                self.assertEqual(repos.search_criteria.list_by_user(user["id"])[0]["id"], "crit_001")
                self.assertEqual(updated_listing["status"], "saved")
                self.assertEqual(listing_search_total, 1)
                self.assertEqual(listing_search_rows[0]["id"], "lst_001")
                self.assertEqual(found_listing["id"], "lst_001")
                self.assertEqual(events[0]["id"], "evt_001")
                self.assertEqual(counts["market_watches"], 1)
                self.assertEqual(counts["listings"], 1)
                self.assertEqual(counts["pending_checks"], 1)
                self.assertEqual(counts["unread_notifications"], 1)
                self.assertEqual(idempotency_key["resource_id"], run["id"])
                self.assertEqual(found_document["detected_type"], "payslip")
                self.assertEqual(active_documents[0]["id"], "doc_001")
                self.assertEqual(latest_snapshot["id"], snapshot["id"])
                self.assertEqual(found_packet["id"], packet["id"])
                self.assertEqual(pending_checks[0]["id"], "chk_001")
            finally:
                connection.close()

    def test_dashboard_repository_reads_seeded_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            connection = create_connection(tmp_path / "dossieragent.db")
            try:
                seed_demo_data(connection, storage_path=tmp_path / "storage")
                dashboard = build_repositories(connection).dashboard

                self.assertEqual(dashboard.current_watch("usr_demo")["id"], "watch_toulouse_t2")
                self.assertEqual(dashboard.latest_run("usr_demo")["id"], "run_latest")
                self.assertEqual(
                    dashboard.latest_dossier_snapshot("usr_demo")["id"],
                    "snap_demo_latest",
                )
                self.assertEqual(len(dashboard.recommended_listings("usr_demo")), 4)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()

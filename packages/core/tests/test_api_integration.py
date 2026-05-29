from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from dossieragent_core.api import create_app
from dossieragent_database import create_connection
from dossieragent_database.seed import seed_demo_data
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
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
    }
    with patch.dict(os.environ, env):
        with TestClient(create_app()) as test_client:
            yield test_client


def test_health_and_dashboard_read_from_seeded_sqlite(client: TestClient) -> None:
    health = client.get("/health")
    dashboard = client.get("/api/v1/dashboard")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "dossieragent-core"}

    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["current_watch"]["id"] == "watch_toulouse_t2"
    assert payload["latest_run"]["stats"]["duplicates"] == 8
    assert payload["dossier"]["readiness_score"] == 78
    assert payload["pending_checks"] == 3
    assert payload["notifications_unread"] == 5


def test_run_now_exposes_run_detail_events_and_idempotency(client: TestClient) -> None:
    first = client.post(
        "/api/v1/market-watches/watch_toulouse_t2/run-now",
        headers={"Idempotency-Key": "integration-run-now"},
    )
    replay = client.post(
        "/api/v1/market-watches/watch_toulouse_t2/run-now",
        headers={"Idempotency-Key": "integration-run-now"},
    )
    conflict = client.post(
        "/api/v1/market-watches/watch_toulouse_t2/run-now",
        headers={"Idempotency-Key": "integration-run-now-conflict"},
    )

    assert first.status_code == 202
    run_id = first.json()["run_id"]
    assert first.json()["status"] == "running"
    assert first.json()["idempotent_replay"] is False

    assert replay.status_code == 202
    assert replay.json()["run_id"] == run_id
    assert replay.json()["idempotent_replay"] is True

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "run_already_active"

    detail = client.get(f"/api/v1/agent-runs/{run_id}")
    events = client.get(f"/api/v1/agent-runs/{run_id}/events")
    assert detail.status_code == 200
    assert detail.json()["id"] == run_id
    assert detail.json()["trigger_type"] == "manual"
    assert detail.json()["current_step"] == "accepted"
    assert events.status_code == 200
    assert [event["type"] for event in events.json()["items"]] == [
        "run_accepted",
        "worker_pending",
    ]


def test_listing_decision_round_trip_persists_to_sqlite(client: TestClient) -> None:
    listing_list = client.get("/api/v1/listings", params={"status": "recommended", "limit": 2})
    detail_before = client.get("/api/v1/listings/lst_001")
    decision = client.patch("/api/v1/listings/lst_001", json={"status": "saved"})
    detail_after = client.get("/api/v1/listings/lst_001")

    assert listing_list.status_code == 200
    payload = listing_list.json()
    assert payload["source"] == "sqlite"
    assert payload["total"] == 4
    assert [item["id"] for item in payload["items"]] == ["lst_001", "lst_002"]

    assert detail_before.status_code == 200
    assert detail_before.json()["status"] == "recommended"
    assert "Sous le budget maximum" in detail_before.json()["explanation"]

    assert decision.status_code == 200
    assert decision.json()["status"] == "saved"
    assert detail_after.status_code == 200
    assert detail_after.json()["status"] == "saved"


def test_dossier_readiness_reanalysis_updates_latest_snapshot(client: TestClient) -> None:
    initial = client.get("/api/v1/dossier/readiness")
    analyzed = client.post("/api/v1/dossier/analyze")
    latest = client.get("/api/v1/dossier/readiness")

    assert initial.status_code == 200
    assert initial.json()["readiness_score"] == 78
    assert initial.json()["missing_docs"] == ["employment_contract", "latest_tax_notice"]

    assert analyzed.status_code == 201
    analyzed_payload = analyzed.json()
    assert analyzed_payload["readiness_score"] == 78
    assert analyzed_payload["can_contact"] is True
    assert analyzed_payload["can_send_full_dossier"] is False
    assert analyzed_payload["missing_docs"] == ["employment_contract", "latest_tax_notice"]

    assert latest.status_code == 200
    assert latest.json()["snapshot_id"] == analyzed_payload["snapshot_id"]


def test_user_check_completion_removes_item_from_pending_list(client: TestClient) -> None:
    pending_before = client.get("/api/v1/user-checks")
    assert pending_before.status_code == 200
    check_id = pending_before.json()["items"][0]["id"]

    completed = client.post(
        f"/api/v1/user-checks/{check_id}/complete",
        json={"decision": "approved", "note": "Verified by integration test."},
    )
    pending_after = client.get("/api/v1/user-checks")

    assert len(pending_before.json()["items"]) == 3

    assert completed.status_code == 200
    completed_payload = completed.json()
    assert completed_payload["id"] == check_id
    assert completed_payload["status"] == "completed"
    assert completed_payload["completed_with"] == "approved"
    assert completed_payload["completed_note"] == "Verified by integration test."

    assert pending_after.status_code == 200
    assert len(pending_after.json()["items"]) == 2
    assert check_id not in {item["id"] for item in pending_after.json()["items"]}

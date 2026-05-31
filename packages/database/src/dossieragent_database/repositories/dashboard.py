from __future__ import annotations

import sqlite3
from typing import Any

from .base import row_to_dict, rows_to_dicts


class DashboardRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def counts_for_user(self, user_id: str) -> dict[str, Any]:
        return {
            "market_watches": self.count("market_watches", user_id),
            "listings": self.count("listings", user_id),
            "documents": self.count("dossier_documents", user_id),
            "contact_packets": self.count("contact_packets", user_id),
            "pending_checks": self.count("user_checks", user_id, "status = 'pending'"),
            "unread_notifications": self.count("notifications", user_id, "read_at IS NULL"),
        }

    def current_watch(self, user_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, name, status, next_run_at, last_run_at
            FROM market_watches
            WHERE user_id = ? AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return None if row is None else row_to_dict(row)

    def latest_run(self, user_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, status, summary_json, created_at, updated_at, completed_at
            FROM agent_runs
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return None if row is None else row_to_dict(row)

    def latest_dossier_snapshot(self, user_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, readiness_score, can_contact, can_send_full_dossier,
                   missing_documents_json, valid_documents_json, recommendations_json, created_at
            FROM dossier_snapshots
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return None if row is None else row_to_dict(row)

    def recommended_listings(self, user_id: str, *, limit: int = 4) -> tuple[dict[str, Any], ...]:
        rows = self.connection.execute(
            """
            SELECT id, title, city, district, price, currency, surface, rooms, status,
                   fit_score, fit_level, risk_flags_json, explanation_json,
                   source_url, canonical_url, raw_payload_json
            FROM listings
            WHERE user_id = ? AND status = 'recommended'
            ORDER BY fit_score DESC, updated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return rows_to_dicts(rows)

    def count(self, table_name: str, user_id: str, where: str | None = None) -> int:
        where_sql = "WHERE user_id = ?"
        if where:
            where_sql = f"{where_sql} AND ({where})"
        row = self.connection.execute(
            f"SELECT COUNT(*) AS count FROM {table_name} {where_sql}",
            (user_id,),
        ).fetchone()
        return int(row["count"])

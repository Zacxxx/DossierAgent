from __future__ import annotations

import sqlite3
from typing import Any


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

    def count(self, table_name: str, user_id: str, where: str | None = None) -> int:
        where_sql = "WHERE user_id = ?"
        if where:
            where_sql = f"{where_sql} AND ({where})"
        row = self.connection.execute(
            f"SELECT COUNT(*) AS count FROM {table_name} {where_sql}",
            (user_id,),
        ).fetchone()
        return int(row["count"])


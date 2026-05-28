from __future__ import annotations

import sqlite3
from typing import Any

from .base import SQLiteTableRepository, row_to_dict


class NotificationRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "notifications")

    def find_for_user(self, *, user_id: str, notification_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM notifications
            WHERE user_id = ? AND id = ?
            LIMIT 1
            """,
            (user_id, notification_id),
        ).fetchone()
        return None if row is None else row_to_dict(row)

    def list_for_user(
        self,
        user_id: str,
        *,
        unread_only: bool = False,
        limit: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        where_sql = "WHERE user_id = ?"
        params: list[Any] = [user_id]
        if unread_only:
            where_sql = f"{where_sql} AND read_at IS NULL"

        rows = self.connection.execute(
            f"""
            SELECT * FROM notifications
            {where_sql}
            ORDER BY created_at DESC, id ASC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return tuple(row_to_dict(row) for row in rows)

    def mark_read(self, *, notification_id: str, read_at: str) -> dict[str, Any]:
        self.connection.execute(
            """
            UPDATE notifications
            SET read_at = COALESCE(read_at, ?)
            WHERE id = ?
            """,
            (read_at, notification_id),
        )
        return self.get(notification_id)

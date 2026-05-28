from __future__ import annotations

import sqlite3
from typing import Any

from .base import SQLiteTableRepository, row_to_dict


class UserCheckRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "user_checks")

    def find_for_user(self, *, user_id: str, check_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM user_checks
            WHERE user_id = ? AND id = ?
            LIMIT 1
            """,
            (user_id, check_id),
        ).fetchone()
        return None if row is None else row_to_dict(row)

    def list_pending_for_user(self, user_id: str, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        rows = self.connection.execute(
            """
            SELECT * FROM user_checks
            WHERE user_id = ? AND status = 'pending'
            ORDER BY created_at DESC, id ASC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return tuple(row_to_dict(row) for row in rows)

    def complete(
        self,
        *,
        check_id: str,
        decision: str,
        note: str | None,
        completed_at: str,
    ) -> dict[str, Any]:
        self.connection.execute(
            """
            UPDATE user_checks
            SET status = 'completed',
                completed_with = ?,
                completed_note = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (decision, note, completed_at, check_id),
        )
        return self.get(check_id)

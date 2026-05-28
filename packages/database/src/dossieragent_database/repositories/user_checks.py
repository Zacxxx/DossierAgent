from __future__ import annotations

import sqlite3
from typing import Any

from .base import SQLiteTableRepository, row_to_dict


class UserCheckRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "user_checks")

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

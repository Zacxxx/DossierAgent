from __future__ import annotations

import sqlite3
from typing import Any

from .base import SQLiteTableRepository, row_to_dict


class IdempotencyKeyRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "idempotency_keys")

    def find_key(
        self,
        *,
        user_id: str,
        scope: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM idempotency_keys
            WHERE user_id = ? AND scope = ? AND idempotency_key = ?
            LIMIT 1
            """,
            (user_id, scope, idempotency_key),
        ).fetchone()
        return None if row is None else row_to_dict(row)


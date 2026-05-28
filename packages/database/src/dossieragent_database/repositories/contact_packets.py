from __future__ import annotations

import sqlite3
from typing import Any

from .base import SQLiteTableRepository, row_to_dict


class ContactPacketRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "contact_packets")

    def find_for_user(self, *, user_id: str, packet_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM contact_packets
            WHERE user_id = ? AND id = ?
            LIMIT 1
            """,
            (user_id, packet_id),
        ).fetchone()
        return None if row is None else row_to_dict(row)

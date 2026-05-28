from __future__ import annotations

import sqlite3
from typing import Any

from .base import SQLiteTableRepository, row_to_dict


class DossierDocumentRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "dossier_documents")

    def find_for_user(self, *, user_id: str, document_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM dossier_documents
            WHERE user_id = ? AND id = ?
            LIMIT 1
            """,
            (user_id, document_id),
        ).fetchone()
        return None if row is None else row_to_dict(row)

    def list_active_for_user(self, user_id: str, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        rows = self.connection.execute(
            """
            SELECT * FROM dossier_documents
            WHERE user_id = ? AND status != 'deleted'
            ORDER BY created_at DESC, id ASC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return tuple(row_to_dict(row) for row in rows)


class DossierSnapshotRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "dossier_snapshots")

    def latest_for_user(self, user_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM dossier_snapshots
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return None if row is None else row_to_dict(row)

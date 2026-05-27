from __future__ import annotations

import sqlite3
from typing import Any

from .base import SQLiteTableRepository, rows_to_dicts


class AgentRunRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "agent_runs")

    def latest_for_user(self, user_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM agent_runs
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return None if row is None else {key: row[key] for key in row.keys()}

    def active_for_watch(self, *, user_id: str, watch_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM agent_runs
            WHERE user_id = ?
              AND watch_id = ?
              AND status IN ('queued', 'running', 'waiting_for_review')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, watch_id),
        ).fetchone()
        return None if row is None else {key: row[key] for key in row.keys()}


class AgentEventRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "agent_events")

    def list_for_run(self, run_id: str) -> tuple[dict[str, Any], ...]:
        rows = self.connection.execute(
            """
            SELECT * FROM agent_events
            WHERE run_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (run_id,),
        ).fetchall()
        return rows_to_dicts(rows)

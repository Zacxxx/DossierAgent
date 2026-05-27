from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any


class SQLiteTableRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        *,
        id_column: str = "id",
        user_scoped: bool = True,
    ) -> None:
        validate_identifier(table_name)
        validate_identifier(id_column)
        self.connection = connection
        self.table_name = table_name
        self.id_column = id_column
        self.user_scoped = user_scoped

    def create(self, data: Mapping[str, Any]) -> dict[str, Any]:
        if not data:
            raise ValueError("Cannot insert an empty row.")

        columns = tuple(data.keys())
        for column in columns:
            validate_identifier(column)

        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        values = tuple(data[column] for column in columns)
        self.connection.execute(
            f"INSERT INTO {self.table_name} ({column_sql}) VALUES ({placeholders})",
            values,
        )
        return self.get(str(data[self.id_column]))

    def get(self, resource_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            f"SELECT * FROM {self.table_name} WHERE {self.id_column} = ?",
            (resource_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"{self.table_name} not found: {resource_id}")
        return row_to_dict(row)

    def find(self, resource_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT * FROM {self.table_name} WHERE {self.id_column} = ?",
            (resource_id,),
        ).fetchone()
        return None if row is None else row_to_dict(row)

    def list_by_user(
        self,
        user_id: str,
        *,
        limit: int = 100,
        order_by: str = "created_at",
        descending: bool = True,
    ) -> tuple[dict[str, Any], ...]:
        if not self.user_scoped:
            raise ValueError(f"{self.table_name} is not user scoped.")

        validate_identifier(order_by)
        direction = "DESC" if descending else "ASC"
        rows = self.connection.execute(
            f"""
            SELECT * FROM {self.table_name}
            WHERE user_id = ?
            ORDER BY {order_by} {direction}
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return tuple(row_to_dict(row) for row in rows)

    def update(self, resource_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        if not data:
            return self.get(resource_id)

        for column in data:
            validate_identifier(column)

        assignments = ", ".join(f"{column} = ?" for column in data)
        values = tuple(data.values()) + (resource_id,)
        self.connection.execute(
            f"UPDATE {self.table_name} SET {assignments} WHERE {self.id_column} = ?",
            values,
        )
        return self.get(resource_id)

    def count_by_user(self, user_id: str, *, where: str | None = None) -> int:
        if not self.user_scoped:
            raise ValueError(f"{self.table_name} is not user scoped.")

        params: list[Any] = [user_id]
        where_sql = "WHERE user_id = ?"
        if where:
            where_sql = f"{where_sql} AND ({where})"

        row = self.connection.execute(
            f"SELECT COUNT(*) AS count FROM {self.table_name} {where_sql}",
            params,
        ).fetchone()
        return int(row["count"])


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: Sequence[sqlite3.Row]) -> tuple[dict[str, Any], ...]:
    return tuple(row_to_dict(row) for row in rows)


def validate_identifier(identifier: str) -> None:
    if not identifier or not identifier.replace("_", "").isalnum() or identifier[0].isdigit():
        raise ValueError(f"Unsafe SQL identifier: {identifier}")

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from .base import SQLiteTableRepository, row_to_dict, rows_to_dicts


class ListingRepository(SQLiteTableRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection, "listings")

    def find_for_user(self, *, user_id: str, listing_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM listings
            WHERE user_id = ? AND id = ?
            LIMIT 1
            """,
            (user_id, listing_id),
        ).fetchone()
        return None if row is None else row_to_dict(row)

    def search(
        self,
        *,
        user_id: str,
        filters: Mapping[str, Any],
        limit: int,
        offset: int,
    ) -> tuple[tuple[dict[str, Any], ...], int]:
        where_sql, params = listing_filter_sql(user_id=user_id, filters=filters)
        count_row = self.connection.execute(
            f"SELECT COUNT(*) AS count FROM listings {where_sql}",
            params,
        ).fetchone()
        rows = self.connection.execute(
            f"""
            SELECT * FROM listings
            {where_sql}
            ORDER BY
              CASE WHEN fit_score IS NULL THEN 1 ELSE 0 END ASC,
              fit_score DESC,
              first_seen_at DESC,
              id ASC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
        return rows_to_dicts(rows), int(count_row["count"])


def listing_filter_sql(*, user_id: str, filters: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
    clauses = ["user_id = ?"]
    params: list[Any] = [user_id]

    for field_name in ("status", "city", "district", "watch_id"):
        value = clean_string(filters.get(field_name))
        if value is not None:
            clauses.append(f"{field_name} = ?")
            params.append(value)

    q = clean_string(filters.get("q"))
    if q is not None:
        clauses.append("(title LIKE ? OR description LIKE ? OR agency_name LIKE ?)")
        query = f"%{q}%"
        params.extend([query, query, query])

    numeric_filters = (
        ("max_price", "price", "<="),
        ("min_price", "price", ">="),
        ("min_surface", "surface", ">="),
        ("min_score", "fit_score", ">="),
    )
    for filter_name, column_name, operator in numeric_filters:
        value = filters.get(filter_name)
        if value is not None:
            clauses.append(f"{column_name} {operator} ?")
            params.append(value)

    return f"WHERE {' AND '.join(clauses)}", tuple(params)


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None

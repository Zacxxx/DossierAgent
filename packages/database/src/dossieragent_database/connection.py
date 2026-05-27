from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DATABASE_PATH = Path("data/dossieragent.db")
DATABASE_PATH_ENV = "DOSSIERAGENT_SQLITE_PATH"
LEGACY_DATABASE_PATH_ENV = "SQLITE_PATH"


def resolve_database_path(database_path: str | os.PathLike[str] | None = None) -> Path | str:
    if database_path is not None:
        return _normalize_path(database_path)

    configured_path = os.environ.get(DATABASE_PATH_ENV) or os.environ.get(LEGACY_DATABASE_PATH_ENV)
    if configured_path:
        return _normalize_path(configured_path)

    return DEFAULT_DATABASE_PATH


def create_connection(
    database_path: str | os.PathLike[str] | None = None,
    *,
    timeout: float = 30.0,
) -> sqlite3.Connection:
    resolved_path = resolve_database_path(database_path)
    if isinstance(resolved_path, Path):
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

    uri = isinstance(resolved_path, str) and resolved_path.startswith("file:")
    connection = sqlite3.connect(resolved_path, timeout=timeout, uri=uri)
    connection.row_factory = sqlite3.Row
    apply_pragmas(connection)
    return connection


def apply_pragmas(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA synchronous=NORMAL")


def _normalize_path(path: str | os.PathLike[str]) -> Path | str:
    raw_path = os.fspath(path)
    if raw_path == ":memory:" or raw_path.startswith("file:"):
        return raw_path
    return Path(raw_path)

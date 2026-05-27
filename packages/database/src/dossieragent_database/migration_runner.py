from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at TEXT NOT NULL
);
"""


class MigrationChecksumMismatch(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    sql: str
    checksum: str

    @classmethod
    def from_file(cls, path: Path) -> "Migration":
        sql = path.read_text(encoding="utf-8")
        version = path.stem.split("_", 1)[0]
        return cls(
            version=version,
            name=path.name,
            sql=sql,
            checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    version: str
    name: str
    checksum: str
    applied_at: str


def run_migrations(
    connection: sqlite3.Connection,
    migrations_path: str | Path | None = None,
) -> tuple[AppliedMigration, ...]:
    ensure_migrations_table(connection)
    applied = load_applied_migrations(connection)
    migrations = load_migrations(migrations_path or default_migrations_path())
    applied_now: list[AppliedMigration] = []

    for migration in migrations:
        existing = applied.get(migration.version)
        if existing is not None:
            if existing.checksum != migration.checksum:
                raise MigrationChecksumMismatch(
                    f"Migration {migration.name} was already applied with a different checksum."
                )
            continue

        applied_now.append(apply_migration(connection, migration))

    return tuple(applied_now)


def default_migrations_path() -> Path:
    return Path(__file__).with_name("migrations")


def load_migrations(migrations_path: str | Path) -> tuple[Migration, ...]:
    path = Path(migrations_path)
    if not path.exists():
        return ()

    return tuple(Migration.from_file(file_path) for file_path in sorted(path.glob("*.sql")))


def ensure_migrations_table(connection: sqlite3.Connection) -> None:
    connection.execute(MIGRATIONS_TABLE_SQL)
    connection.commit()


def load_applied_migrations(connection: sqlite3.Connection) -> dict[str, AppliedMigration]:
    rows = connection.execute(
        "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {
        str(row["version"]): AppliedMigration(
            version=str(row["version"]),
            name=str(row["name"]),
            checksum=str(row["checksum"]),
            applied_at=str(row["applied_at"]),
        )
        for row in rows
    }


def apply_migration(connection: sqlite3.Connection, migration: Migration) -> AppliedMigration:
    applied_at = datetime.now(UTC).isoformat()
    connection.executescript(migration.sql)
    connection.execute(
        """
        INSERT INTO schema_migrations (version, name, checksum, applied_at)
        VALUES (?, ?, ?, ?)
        """,
        (migration.version, migration.name, migration.checksum, applied_at),
    )
    connection.commit()
    return AppliedMigration(
        version=migration.version,
        name=migration.name,
        checksum=migration.checksum,
        applied_at=applied_at,
    )


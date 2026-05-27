from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dossieragent_database import create_connection, run_migrations


class MigrationRunnerTests(unittest.TestCase):
    def test_run_migrations_applies_ordered_sql_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            migrations_path = tmp_path / "migrations"
            migrations_path.mkdir()
            (migrations_path / "0001_create_example.sql").write_text(
                """
                CREATE TABLE example_items (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL
                );
                INSERT INTO example_items (id, name) VALUES ('one', 'First');
                """,
                encoding="utf-8",
            )
            db_path = tmp_path / "dossieragent.db"

            connection = create_connection(db_path)
            try:
                first_run = run_migrations(connection, migrations_path)
                second_run = run_migrations(connection, migrations_path)

                self.assertEqual(len(first_run), 1)
                self.assertEqual(len(second_run), 0)

                item_count = connection.execute("SELECT COUNT(*) FROM example_items").fetchone()[0]
                migration_count = connection.execute(
                    "SELECT COUNT(*) FROM schema_migrations"
                ).fetchone()[0]

                self.assertEqual(item_count, 1)
                self.assertEqual(migration_count, 1)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dossieragent_database import create_connection, resolve_database_path


class ConnectionTests(unittest.TestCase):
    def test_create_connection_applies_required_pragmas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "dossieragent.db"

            connection = create_connection(db_path)
            try:
                journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
                synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]

                self.assertEqual(journal_mode, "wal")
                self.assertEqual(foreign_keys, 1)
                self.assertEqual(synchronous, 1)
                self.assertIs(connection.row_factory, sqlite3.Row)
            finally:
                connection.close()

    def test_resolve_database_path_uses_explicit_path(self) -> None:
        self.assertEqual(resolve_database_path("custom.db"), Path("custom.db"))

    def test_resolve_database_path_uses_environment(self) -> None:
        with patch.dict("os.environ", {"DOSSIERAGENT_SQLITE_PATH": "from-env.db"}):
            self.assertEqual(resolve_database_path(), Path("from-env.db"))


if __name__ == "__main__":
    unittest.main()

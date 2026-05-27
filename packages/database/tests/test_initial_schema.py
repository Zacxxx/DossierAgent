from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dossieragent_database import create_connection, run_migrations


EXPECTED_TABLES = {
    "schema_migrations",
    "users",
    "refresh_tokens",
    "search_criteria",
    "market_watches",
    "listings",
    "dossier_documents",
    "dossier_snapshots",
    "contact_packets",
    "user_checks",
    "notifications",
    "agent_runs",
    "agent_events",
    "idempotency_keys",
}

EXPECTED_INDEXES = {
    "idx_listings_user_status",
    "idx_listings_canonical_hash",
    "idx_listings_fingerprint",
    "idx_listings_source_listing_id",
    "idx_agent_events_run",
    "idx_idempotency_keys_lookup",
}

EXPECTED_JSON_COLUMNS = {
    "search_criteria": {
        "cities_json",
        "districts_json",
        "languages_json",
        "filters_json",
    },
    "market_watches": {"source_config_json"},
    "listings": {"risk_flags_json", "explanation_json", "raw_payload_json"},
    "dossier_documents": {"issues_json", "warnings_json"},
    "dossier_snapshots": {
        "missing_documents_json",
        "valid_documents_json",
        "recommendations_json",
    },
    "contact_packets": {"questions_json", "dossier_summary_json"},
    "user_checks": {"payload_json"},
    "agent_runs": {"summary_json", "error_json"},
    "agent_events": {"payload_json"},
}


class InitialSchemaTests(unittest.TestCase):
    def test_initial_migration_creates_spec_tables_indexes_and_json_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = create_connection(Path(tmp_dir) / "dossieragent.db")
            try:
                applied = run_migrations(connection)

                self.assertEqual([migration.version for migration in applied], ["0001", "0002"])
                self.assertLessEqual(EXPECTED_TABLES, self.table_names(connection))
                self.assertLessEqual(EXPECTED_INDEXES, self.index_names(connection))

                for table_name, expected_columns in EXPECTED_JSON_COLUMNS.items():
                    self.assertLessEqual(expected_columns, self.column_names(connection, table_name))
            finally:
                connection.close()

    def test_initial_migration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            connection = create_connection(Path(tmp_dir) / "dossieragent.db")
            try:
                first_run = run_migrations(connection)
                second_run = run_migrations(connection)

                self.assertEqual(len(first_run), 2)
                self.assertEqual(len(second_run), 0)
            finally:
                connection.close()

    @staticmethod
    def table_names(connection) -> set[str]:
        rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        return {str(row["name"]) for row in rows}

    @staticmethod
    def index_names(connection) -> set[str]:
        rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        return {str(row["name"]) for row in rows}

    @staticmethod
    def column_names(connection, table_name: str) -> set[str]:
        return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table_name})")}


if __name__ == "__main__":
    unittest.main()

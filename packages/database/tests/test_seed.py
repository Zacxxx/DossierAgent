from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dossieragent_database import create_connection
from dossieragent_database.seed import DEMO_USER_ID, seed_demo_data


class SeedTests(unittest.TestCase):
    def test_seed_demo_data_is_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            connection = create_connection(tmp_path / "dossieragent.db")
            try:
                first_result = seed_demo_data(connection, storage_path=tmp_path / "storage")
                second_result = seed_demo_data(connection, storage_path=tmp_path / "storage")

                self.assertEqual(first_result.counts, second_result.counts)
                self.assertEqual(first_result.counts["users"], 1)
                self.assertEqual(first_result.counts["search_criteria"], 2)
                self.assertEqual(first_result.counts["market_watches"], 2)
                self.assertEqual(first_result.counts["listings"], 30)
                self.assertEqual(first_result.counts["dossier_documents"], 6)
                self.assertEqual(first_result.counts["dossier_snapshots"], 1)
                self.assertEqual(first_result.counts["contact_packets"], 2)
                self.assertEqual(first_result.counts["user_checks"], 3)
                self.assertEqual(first_result.counts["notifications"], 5)
                self.assertEqual(first_result.counts["agent_runs"], 2)
                self.assertEqual(first_result.counts["agent_events"], 10)

                self.assertEqual(self.count_listings_by_status(connection, "recommended"), 4)
                self.assertEqual(self.count_listings_by_status(connection, "duplicate"), 8)
                self.assertEqual(self.count_listings_by_status(connection, "repost"), 4)
                self.assertEqual(self.count_listings_by_status(connection, "trash"), 5)

                extracted_text = tmp_path / "storage" / "extracted_text" / "demo" / "doc_identity.txt"
                self.assertTrue(extracted_text.exists())
                self.assertIn("Carte nationale", extracted_text.read_text(encoding="utf-8"))
            finally:
                connection.close()

    @staticmethod
    def count_listings_by_status(connection, status: str) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count FROM listings
            WHERE user_id = ? AND status = ?
            """,
            (DEMO_USER_ID, status),
        ).fetchone()
        return int(row["count"])


if __name__ == "__main__":
    unittest.main()

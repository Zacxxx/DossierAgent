from __future__ import annotations

import json
import unittest
from typing import Any

from dossieragent_search_engine import (
    build_listing_bulk_ndjson,
    build_listing_bulk_operations,
    bulk_index_listings,
    listing_index_document,
)


class FakeBulkClient:
    def __init__(self) -> None:
        self.operations: tuple[dict[str, Any], ...] = ()
        self.refresh = False

    def bulk(self, *, operations: tuple[dict[str, Any], ...], refresh: bool = False) -> dict[str, Any]:
        self.operations = operations
        self.refresh = refresh
        return {
            "errors": False,
            "items": [
                {"index": {"_id": operations[index]["index"]["_id"], "status": 201}}
                for index in range(0, len(operations), 2)
            ],
        }


class ListingIndexingTests(unittest.TestCase):
    def test_listing_index_document_shapes_sqlite_row_for_elastic_mapping(self) -> None:
        document = listing_index_document(
            {
                "id": "lst_001",
                "user_id": "usr_demo",
                "watch_id": "watch_toulouse_t2",
                "source": "demo_seed",
                "source_url": "https://demo.example/1",
                "canonical_url": "https://demo.example/1",
                "canonical_url_hash": "abc",
                "source_listing_id": "1",
                "composite_fingerprint": "fingerprint",
                "title": "T2 Carmes",
                "description": "Metro proche",
                "city": "Toulouse",
                "district": "Carmes",
                "postal_code": "31000",
                "agency_name": "Demo Immo",
                "price": 780,
                "surface": 42,
                "rooms": 2,
                "status": "recommended",
                "fit_score": 91,
                "first_seen_at": "2026-05-28T10:00:00Z",
                "last_seen_at": "2026-05-29T10:00:00Z",
                "risk_flags_json": "[\"charges_non_detaillees\"]",
            }
        )

        self.assertEqual(document["listing_id"], "lst_001")
        self.assertEqual(document["user_id"], "usr_demo")
        self.assertEqual(document["risk_flags"], ["charges_non_detaillees"])
        self.assertNotIn("raw_payload_json", document)

    def test_bulk_operations_and_ndjson_use_listing_ids_as_document_ids(self) -> None:
        listings = [
            {
                "id": "lst_001",
                "user_id": "usr_demo",
                "title": "T2 Carmes",
                "status": "recommended",
            }
        ]

        operations = build_listing_bulk_operations(index_name="listings_v1", listings=listings)
        ndjson = build_listing_bulk_ndjson(index_name="listings_v1", listings=listings)
        lines = [json.loads(line) for line in ndjson.decode("utf-8").splitlines()]

        self.assertEqual(operations[0], {"index": {"_index": "listings_v1", "_id": "lst_001"}})
        self.assertEqual(operations[1]["listing_id"], "lst_001")
        self.assertEqual(lines, list(operations))

    def test_bulk_index_listings_parses_client_response(self) -> None:
        client = FakeBulkClient()

        result = bulk_index_listings(
            client,
            index_name="listings_v1",
            listings=[
                {"id": "lst_001", "user_id": "usr_demo", "title": "T2", "status": "recommended"},
                {"id": "lst_002", "user_id": "usr_demo", "title": "T3", "status": "saved"},
            ],
            refresh=True,
        )

        self.assertTrue(client.refresh)
        self.assertEqual(len(client.operations), 4)
        self.assertEqual(result.status, "indexed")
        self.assertEqual(result.attempted, 2)
        self.assertEqual(result.indexed, 2)
        self.assertEqual(result.errors, ())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from copy import deepcopy
from typing import Any

from dossieragent_search_engine import ensure_indices, load_mapping, verify_index_mapping
from dossieragent_search_engine.indices import (
    DEFAULT_VECTOR_DIMS,
    DOCUMENTS_INDEX,
    INDEX_NAMES,
    LISTINGS_INDEX,
    IndexMappingMismatch,
)


class FakeIndicesClient:
    def __init__(self, existing: dict[str, dict[str, Any]] | None = None) -> None:
        self.existing = existing or {}
        self.created: dict[str, dict[str, Any]] = {}

    def exists(self, *, index: str) -> bool:
        return index in self.existing

    def create(self, *, index: str, body: dict[str, Any]) -> None:
        self.created[index] = body

    def get_mapping(self, *, index: str) -> dict[str, Any]:
        return {index: self.existing[index]}


class FakeElasticsearchClient:
    def __init__(self, existing: dict[str, dict[str, Any]] | None = None) -> None:
        self.indices = FakeIndicesClient(existing)


class IndexMappingTests(unittest.TestCase):
    def test_mapping_files_define_required_vectors_and_scalar_fields(self) -> None:
        listings = load_mapping(LISTINGS_INDEX)
        documents = load_mapping(DOCUMENTS_INDEX)

        listing_properties = listings["mappings"]["properties"]
        document_properties = documents["mappings"]["properties"]

        self.assertEqual(listing_properties["listing_vector"]["type"], "dense_vector")
        self.assertEqual(listing_properties["listing_vector"]["dims"], DEFAULT_VECTOR_DIMS)
        self.assertTrue(listing_properties["listing_vector"]["index"])
        self.assertEqual(document_properties["content_vector"]["type"], "dense_vector")
        self.assertEqual(document_properties["content_vector"]["dims"], DEFAULT_VECTOR_DIMS)
        self.assertTrue(document_properties["content_vector"]["index"])

        for field_name in (
            "price",
            "surface",
            "rooms",
            "status",
            "city",
            "district",
            "first_seen_at",
            "fit_score",
        ):
            self.assertIn(field_name, listing_properties)

        for field_name in ("status", "declared_type", "detected_type", "page_count", "created_at"):
            self.assertIn(field_name, document_properties)

    def test_ensure_indices_creates_missing_indices(self) -> None:
        client = FakeElasticsearchClient()

        results = ensure_indices(client)

        self.assertEqual([result.index for result in results], list(INDEX_NAMES))
        self.assertEqual([result.status for result in results], ["created", "created"])
        self.assertEqual(set(client.indices.created), set(INDEX_NAMES))

    def test_ensure_indices_verifies_existing_indices(self) -> None:
        existing = {
            LISTINGS_INDEX: load_mapping(LISTINGS_INDEX)["mappings"],
            DOCUMENTS_INDEX: load_mapping(DOCUMENTS_INDEX)["mappings"],
        }
        client = FakeElasticsearchClient(existing)

        results = ensure_indices(client)

        self.assertEqual([result.status for result in results], ["verified", "verified"])
        self.assertEqual(client.indices.created, {})

    def test_verify_index_mapping_rejects_missing_or_wrong_fields(self) -> None:
        mapping = deepcopy(load_mapping(LISTINGS_INDEX))
        del mapping["mappings"]["properties"]["price"]

        with self.assertRaises(IndexMappingMismatch):
            verify_index_mapping(LISTINGS_INDEX, mapping)

        mapping = deepcopy(load_mapping(LISTINGS_INDEX))
        mapping["mappings"]["properties"]["listing_vector"]["dims"] = 384

        with self.assertRaises(IndexMappingMismatch):
            verify_index_mapping(LISTINGS_INDEX, mapping)


if __name__ == "__main__":
    unittest.main()

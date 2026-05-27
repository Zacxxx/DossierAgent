from __future__ import annotations

import unittest

from dossieragent_processing import deduplicate_listing, normalize_listing
from dossieragent_processing.listings import DEFAULT_DEDUPE_THRESHOLDS, DedupeThresholds


class ListingProcessingTests(unittest.TestCase):
    def test_normalize_listing_creates_hash_and_composite_fingerprint(self) -> None:
        normalized = normalize_listing(
            {
                "source": "demo_seed",
                "source_url": "HTTPS://Demo.DossierAgent.Local/listings/001/?utm_source=test",
                "title": "T2 Saint-Cyprien proche metro",
                "description": "Appartement deux pieces proche metro.",
                "city": "Toulouse",
                "district": "Saint-Cyprien",
                "price": "790 EUR",
                "surface": "39 m2",
                "agency_name": "Agence Demo Toulouse",
            }
        )
        normalized_again = normalize_listing(
            {
                "source": "demo_seed",
                "source_url": "https://demo.dossieragent.local/listings/001",
                "title": "T2 Saint Cyprien proche métro",
                "city": "Toulouse",
                "district": "Saint Cyprien",
                "price": 790,
                "surface": 39,
                "agency_name": "Agence Demo Toulouse",
            }
        )

        self.assertEqual(
            normalized.canonical_url,
            "https://demo.dossieragent.local/listings/001",
        )
        self.assertEqual(len(normalized.canonical_url_hash), 64)
        self.assertEqual(len(normalized.composite_fingerprint), 64)
        self.assertEqual(normalized.canonical_url_hash, normalized_again.canonical_url_hash)
        self.assertEqual(normalized.composite_fingerprint, normalized_again.composite_fingerprint)

    def test_exact_duplicate_matches_canonical_url_hash(self) -> None:
        existing = seed_listing("lst_001", source_url="https://demo.test/listings/1")
        candidate = seed_listing(
            "candidate",
            source_url="https://demo.test/listings/1/?utm_campaign=scan",
            source_listing_id="new-id",
        )

        decision = deduplicate_listing(candidate, [existing])

        self.assertEqual(decision.status, "duplicate")
        self.assertEqual(decision.matched_listing_id, "lst_001")
        self.assertIn("canonical_url_hash_match", decision.reasons)

    def test_exact_duplicate_matches_source_listing_id(self) -> None:
        existing = seed_listing("lst_001", source="seloger", source_listing_id="abc-123")
        candidate = seed_listing(
            "candidate",
            source="seloger",
            source_url="https://demo.test/other-url",
            source_listing_id="abc-123",
        )

        decision = deduplicate_listing(candidate, [existing])

        self.assertEqual(decision.status, "duplicate")
        self.assertIn("source_listing_id_match", decision.reasons)

    def test_quasi_exact_detects_repost_with_different_url(self) -> None:
        existing = seed_listing(
            "lst_001",
            title="T2 Saint-Cyprien proche metro",
            description="Deux pieces clair proche metro et commerces.",
        )
        candidate = seed_listing(
            "candidate",
            source_url="https://demo.test/listings/repost",
            source_listing_id="repost-001",
            title="Appartement T2 Saint Cyprien metro",
            description="Deux pieces lumineux proche du metro et commerces.",
        )

        decision = deduplicate_listing(candidate, [existing])

        self.assertEqual(decision.status, "repost")
        self.assertEqual(decision.matched_listing_id, "lst_001")
        self.assertGreaterEqual(decision.score, DEFAULT_DEDUPE_THRESHOLDS.repost_score_min)
        self.assertLess(decision.score, DEFAULT_DEDUPE_THRESHOLDS.duplicate_score)

    def test_quasi_exact_detects_changed_listing_with_price_variation(self) -> None:
        existing = seed_listing("lst_001", price=790)
        candidate = seed_listing(
            "candidate",
            source_url="https://demo.test/listings/changed",
            source_listing_id="changed-001",
            price=830,
        )

        decision = deduplicate_listing(candidate, [existing])

        self.assertEqual(decision.status, "changed_listing")
        self.assertEqual(decision.matched_listing_id, "lst_001")
        self.assertGreaterEqual(
            decision.score,
            DEFAULT_DEDUPE_THRESHOLDS.changed_listing_score_min,
        )

    def test_low_similarity_listing_is_new(self) -> None:
        existing = seed_listing("lst_001")
        candidate = seed_listing(
            "candidate",
            source_url="https://demo.test/listings/new",
            source_listing_id="new-001",
            title="Studio excentre meuble",
            description="Petit studio meuble loin du centre.",
            city="Montauban",
            district="Centre",
            price=520,
            surface=20,
        )

        decision = deduplicate_listing(
            candidate,
            [existing],
            thresholds=DedupeThresholds(repost_score_min=0.82),
        )

        self.assertEqual(decision.status, "new")
        self.assertIsNone(decision.matched_listing_id)


def seed_listing(
    listing_id: str,
    *,
    source: str = "demo_seed",
    source_url: str | None = None,
    source_listing_id: str | None = None,
    title: str = "T2 Saint-Cyprien proche metro",
    description: str = "Appartement deux pieces proche metro et commerces.",
    city: str = "Toulouse",
    district: str = "Saint-Cyprien",
    price: float = 790,
    surface: float = 39,
) -> dict[str, object]:
    return {
        "id": listing_id,
        "source": source,
        "source_url": source_url or f"https://demo.test/listings/{listing_id}",
        "source_listing_id": source_listing_id or f"seed-{listing_id}",
        "title": title,
        "description": description,
        "city": city,
        "district": district,
        "postal_code": "31000",
        "price": price,
        "currency": "EUR",
        "surface": surface,
        "rooms": 2,
        "agency_name": "Agence Demo Toulouse",
    }


if __name__ == "__main__":
    unittest.main()

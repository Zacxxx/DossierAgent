from __future__ import annotations

import unittest

from dossieragent_processing import deduplicate_listing, normalize_listing, rank_listing
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

    def test_rank_listing_strong_match_uses_spec_weights(self) -> None:
        result = rank_listing(
            seed_listing(
                "lst_001",
                title="T2 Saint-Cyprien proche metro avec balcon",
                description="Charges detaillees. Disponible maintenant. Metro et commerces.",
                source_url="https://demo.test/listings/strong",
                contact_hint="Agence joignable par telephone",
                address="12 rue de la Republique",
                first_seen_at="2026-05-27T10:00:00Z",
            ),
            toulouse_criteria(),
            dossier_context={"readiness_score": 78, "can_contact": True},
            now="2026-05-27T16:00:00Z",
        )

        self.assertEqual(result.fit_score, 100)
        self.assertEqual(result.fit_level, "strong")
        self.assertEqual(
            result.factor_scores,
            {
                "budget": 25.0,
                "surface": 20.0,
                "location": 20.0,
                "text_signals": 15.0,
                "freshness": 10.0,
                "dossier_alignment": 10.0,
            },
        )
        self.assertEqual(result.risk_penalty, 0)
        self.assertEqual(result.risk_flags, ())

    def test_rank_listing_risk_penalties_reduce_score(self) -> None:
        safe = rank_listing(
            seed_listing(
                "lst_001",
                title="T2 Saint-Cyprien proche metro avec balcon",
                description="Charges detaillees. Disponible maintenant. Metro et commerces.",
                source_url="https://demo.test/listings/safe",
                contact_hint="Agence joignable par telephone",
                address="12 rue de la Republique",
                first_seen_at="2026-05-27T10:00:00Z",
            ),
            toulouse_criteria(),
            dossier_context={"readiness_score": 78, "can_contact": True},
            now="2026-05-27T16:00:00Z",
        )
        risky = rank_listing(
            seed_listing(
                "lst_002",
                title="T2 Saint-Cyprien proche metro avec balcon",
                description="Metro et commerces.",
                source_url="https://demo.test/listings/risky",
                first_seen_at="2026-05-27T10:00:00Z",
            ),
            toulouse_criteria(),
            dossier_context={"readiness_score": 78, "can_contact": True},
            now="2026-05-27T16:00:00Z",
        )

        self.assertLess(risky.fit_score, safe.fit_score)
        self.assertEqual(risky.risk_penalty, 30)
        self.assertIn("charges_non_detaillees", risky.risk_flags)
        self.assertIn("contact_absent", risky.risk_flags)

    def test_rank_listing_low_match_stays_low(self) -> None:
        result = rank_listing(
            seed_listing(
                "lst_003",
                title="Studio meuble excentre",
                description="Petit studio meuble loin du centre.",
                source_url="https://demo.test/listings/low",
                city="Montauban",
                district="Centre",
                price=930,
                surface=20,
                first_seen_at="2026-05-01T10:00:00Z",
            ),
            toulouse_criteria(),
            dossier_context={"readiness_score": 30, "can_contact": False},
            now="2026-05-27T16:00:00Z",
        )

        self.assertEqual(result.fit_level, "low")
        self.assertEqual(result.factor_scores["budget"], 0)
        self.assertEqual(result.factor_scores["surface"], 0)
        self.assertEqual(result.factor_scores["location"], 0)
        self.assertLess(result.fit_score, 50)


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
    contact_hint: str | None = None,
    address: str | None = None,
    first_seen_at: str | None = None,
) -> dict[str, object]:
    listing: dict[str, object] = {
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
    if contact_hint is not None:
        listing["contact_hint"] = contact_hint
    if address is not None:
        listing["address"] = address
    if first_seen_at is not None:
        listing["first_seen_at"] = first_seen_at
    return listing


def toulouse_criteria() -> dict[str, object]:
    return {
        "cities": ["Toulouse"],
        "districts": ["Saint-Cyprien", "Carmes", "Minimes"],
        "budget_max": 850,
        "surface_min": 35,
        "filters": {"must_have": ["metro", "balcon"], "avoid": ["meuble obligatoire"]},
    }


if __name__ == "__main__":
    unittest.main()

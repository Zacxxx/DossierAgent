from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

from .normalization import NormalizedListing, normalize_listing, normalize_text

DedupeStatus = Literal["duplicate", "repost", "changed_listing", "new"]


@dataclass(frozen=True, slots=True)
class DedupeThresholds:
    duplicate_score: float = 0.92
    repost_score_min: float = 0.82
    changed_listing_score_min: float = 0.75
    numeric_change_min_ratio: float = 0.02
    numeric_change_min_absolute: float = 1.0


DEFAULT_DEDUPE_THRESHOLDS = DedupeThresholds()


@dataclass(frozen=True, slots=True)
class DedupeDecision:
    status: DedupeStatus
    matched_listing_id: str | None
    score: float
    reasons: tuple[str, ...]
    similarity: Mapping[str, float]

    @property
    def is_existing_listing(self) -> bool:
        return self.status in {"duplicate", "repost", "changed_listing"}


def deduplicate_listing(
    candidate: NormalizedListing | Mapping[str, Any],
    existing_listings: Iterable[NormalizedListing | Mapping[str, Any]],
    *,
    thresholds: DedupeThresholds = DEFAULT_DEDUPE_THRESHOLDS,
) -> DedupeDecision:
    normalized_candidate = coerce_listing(candidate)
    normalized_existing = tuple(coerce_listing(existing) for existing in existing_listings)

    exact_decision = exact_duplicate_decision(normalized_candidate, normalized_existing)
    if exact_decision is not None:
        return exact_decision

    if not normalized_existing:
        return new_decision()

    scored = tuple(
        (existing, listing_similarity(normalized_candidate, existing))
        for existing in normalized_existing
    )
    best_existing, best_similarity = max(scored, key=lambda item: item[1]["score"])
    best_score = best_similarity["score"]
    matched_id = listing_id(best_existing)
    numeric_changed = has_numeric_change(normalized_candidate, best_existing, thresholds)

    if best_existing.composite_fingerprint == normalized_candidate.composite_fingerprint:
        return DedupeDecision(
            status="duplicate",
            matched_listing_id=matched_id,
            score=1.0,
            reasons=("composite_fingerprint_match",),
            similarity=best_similarity,
        )

    if numeric_changed and best_score >= thresholds.changed_listing_score_min:
        return DedupeDecision(
            status="changed_listing",
            matched_listing_id=matched_id,
            score=best_score,
            reasons=("similar_listing_with_price_or_surface_change",),
            similarity=best_similarity,
        )

    if best_score >= thresholds.duplicate_score:
        return DedupeDecision(
            status="duplicate",
            matched_listing_id=matched_id,
            score=best_score,
            reasons=("probable_duplicate_similarity_threshold",),
            similarity=best_similarity,
        )

    if best_score >= thresholds.repost_score_min:
        return DedupeDecision(
            status="repost",
            matched_listing_id=matched_id,
            score=best_score,
            reasons=("same_listing_reposted_with_different_url",),
            similarity=best_similarity,
        )

    return DedupeDecision(
        status="new",
        matched_listing_id=None,
        score=best_score,
        reasons=("below_similarity_threshold",),
        similarity=best_similarity,
    )


def exact_duplicate_decision(
    candidate: NormalizedListing,
    existing_listings: Iterable[NormalizedListing],
) -> DedupeDecision | None:
    for existing in existing_listings:
        matched_id = listing_id(existing)
        if candidate.canonical_url_hash == existing.canonical_url_hash:
            return DedupeDecision(
                status="duplicate",
                matched_listing_id=matched_id,
                score=1.0,
                reasons=("canonical_url_hash_match",),
                similarity={"score": 1.0},
            )
        if (
            candidate.source_listing_id
            and existing.source_listing_id
            and candidate.source == existing.source
            and candidate.source_listing_id == existing.source_listing_id
        ):
            return DedupeDecision(
                status="duplicate",
                matched_listing_id=matched_id,
                score=1.0,
                reasons=("source_listing_id_match",),
                similarity={"score": 1.0},
            )
    return None


def listing_similarity(
    candidate: NormalizedListing,
    existing: NormalizedListing,
) -> dict[str, float]:
    title_similarity = string_similarity(candidate.normalized_title, existing.normalized_title)
    description_similarity = string_similarity(
        normalize_text(candidate.description or ""),
        normalize_text(existing.description or ""),
    )
    price_proximity = numeric_proximity(candidate.price, existing.price)
    surface_proximity = numeric_proximity(candidate.surface, existing.surface)
    location_similarity = string_similarity(
        " ".join(
            (
                normalize_text(candidate.city or ""),
                normalize_text(candidate.district or ""),
                normalize_text(candidate.postal_code or ""),
            )
        ),
        " ".join(
            (
                normalize_text(existing.city or ""),
                normalize_text(existing.district or ""),
                normalize_text(existing.postal_code or ""),
            )
        ),
    )
    score = (
        0.35 * title_similarity
        + 0.25 * description_similarity
        + 0.15 * price_proximity
        + 0.15 * surface_proximity
        + 0.10 * location_similarity
    )
    return {
        "score": round(score, 6),
        "title_similarity": round(title_similarity, 6),
        "description_similarity": round(description_similarity, 6),
        "price_proximity": round(price_proximity, 6),
        "surface_proximity": round(surface_proximity, 6),
        "location_similarity": round(location_similarity, 6),
    }


def coerce_listing(value: NormalizedListing | Mapping[str, Any]) -> NormalizedListing:
    if isinstance(value, NormalizedListing):
        return value
    return normalize_listing(value)


def string_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def numeric_proximity(left: float | None, right: float | None) -> float:
    if left is None and right is None:
        return 1.0
    if left is None or right is None:
        return 0.0
    denominator = max(abs(left), abs(right), 1.0)
    return max(0.0, 1.0 - min(abs(left - right) / denominator, 1.0))


def has_numeric_change(
    candidate: NormalizedListing,
    existing: NormalizedListing,
    thresholds: DedupeThresholds,
) -> bool:
    return numeric_changed(candidate.price, existing.price, thresholds) or numeric_changed(
        candidate.surface,
        existing.surface,
        thresholds,
    )


def numeric_changed(
    left: float | None,
    right: float | None,
    thresholds: DedupeThresholds,
) -> bool:
    if left is None or right is None:
        return False
    absolute_delta = abs(left - right)
    denominator = max(abs(left), abs(right), 1.0)
    return (
        absolute_delta >= thresholds.numeric_change_min_absolute
        and absolute_delta / denominator >= thresholds.numeric_change_min_ratio
    )


def listing_id(listing: NormalizedListing) -> str | None:
    raw_id = listing.raw_payload.get("id") or listing.raw_payload.get("listing_id")
    return None if raw_id is None else str(raw_id)


def new_decision() -> DedupeDecision:
    return DedupeDecision(
        status="new",
        matched_listing_id=None,
        score=0.0,
        reasons=("no_existing_listings",),
        similarity={"score": 0.0},
    )

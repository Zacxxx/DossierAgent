from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from .normalization import NormalizedListing, normalize_listing, normalize_text, parse_float

FitLevel = Literal["strong", "medium", "low"]

RANKING_WEIGHTS: dict[str, float] = {
    "budget": 25.0,
    "surface": 20.0,
    "location": 20.0,
    "text_signals": 15.0,
    "freshness": 10.0,
    "dossier_alignment": 10.0,
}

RISK_PENALTIES: dict[str, float] = {
    "charges_non_detaillees": 7.5,
    "disponibilite_non_precisee": 7.5,
    "adresse_imprecise": 7.5,
    "contact_absent": 7.5,
    "avoid_keyword_present": 10.0,
}

MAX_RISK_PENALTY = 30.0
DEFAULT_TEXT_SIGNALS = (
    "metro",
    "tram",
    "balcon",
    "calme",
    "lumineux",
    "commerces",
    "ligne b",
    "parking",
)


@dataclass(frozen=True, slots=True)
class RankingResult:
    fit_score: float
    fit_level: FitLevel
    factor_scores: Mapping[str, float]
    risk_penalty: float
    risk_flags: tuple[str, ...]
    reasons: tuple[str, ...]


def rank_listing(
    listing: NormalizedListing | Mapping[str, Any],
    criteria: Mapping[str, Any],
    *,
    dossier_context: Mapping[str, Any] | None = None,
    now: str | datetime | None = None,
) -> RankingResult:
    normalized_listing = coerce_listing(listing)
    normalized_criteria = normalize_criteria(criteria)
    effective_now = coerce_datetime(now or datetime.now(UTC))

    factor_scores = {
        "budget": budget_score(normalized_listing, normalized_criteria),
        "surface": surface_score(normalized_listing, normalized_criteria),
        "location": location_score(normalized_listing, normalized_criteria),
        "text_signals": text_signal_score(normalized_listing, normalized_criteria),
        "freshness": freshness_score(normalized_listing, effective_now),
        "dossier_alignment": dossier_alignment_score(dossier_context),
    }
    risk_flags = detect_risk_flags(normalized_listing, normalized_criteria)
    risk_penalty = min(
        MAX_RISK_PENALTY,
        sum(RISK_PENALTIES.get(flag, 0.0) for flag in risk_flags),
    )
    score = clamp_score(sum(factor_scores.values()) - risk_penalty)

    return RankingResult(
        fit_score=score,
        fit_level=fit_level(score),
        factor_scores={key: round(value, 2) for key, value in factor_scores.items()},
        risk_penalty=round(risk_penalty, 2),
        risk_flags=risk_flags,
        reasons=build_reasons(factor_scores, risk_flags),
    )


def normalize_criteria(criteria: Mapping[str, Any]) -> dict[str, Any]:
    filters = mapping_field(criteria, "filters", "filters_json")
    return {
        "budget_max": parse_float(criteria.get("budget_max")),
        "surface_min": parse_float(criteria.get("surface_min")),
        "cities": tuple(normalize_text(value) for value in sequence_field(criteria, "cities", "cities_json")),
        "districts": tuple(
            normalize_text(value) for value in sequence_field(criteria, "districts", "districts_json")
        ),
        "must_have": tuple(normalize_text(value) for value in sequence_value(filters.get("must_have"))),
        "avoid": tuple(normalize_text(value) for value in sequence_value(filters.get("avoid"))),
    }


def budget_score(listing: NormalizedListing, criteria: Mapping[str, Any]) -> float:
    budget_max = criteria.get("budget_max")
    if listing.price is None or not isinstance(budget_max, float):
        return 0.0
    return RANKING_WEIGHTS["budget"] if listing.price <= budget_max else 0.0


def surface_score(listing: NormalizedListing, criteria: Mapping[str, Any]) -> float:
    surface_min = criteria.get("surface_min")
    if listing.surface is None or not isinstance(surface_min, float):
        return 0.0
    return RANKING_WEIGHTS["surface"] if listing.surface >= surface_min else 0.0


def location_score(listing: NormalizedListing, criteria: Mapping[str, Any]) -> float:
    target_cities = set(criteria.get("cities", ()))
    target_districts = set(criteria.get("districts", ()))
    listing_city = normalize_text(listing.city or "")
    listing_district = normalize_text(listing.district or "")

    city_matches = not target_cities or listing_city in target_cities
    district_matches = not target_districts or listing_district in target_districts
    if city_matches and district_matches:
        return RANKING_WEIGHTS["location"]
    if city_matches:
        return 12.0
    return 0.0


def text_signal_score(listing: NormalizedListing, criteria: Mapping[str, Any]) -> float:
    signals = criteria.get("must_have") or tuple(normalize_text(value) for value in DEFAULT_TEXT_SIGNALS)
    if not signals:
        return 0.0

    haystack = listing_text(listing)
    matched = sum(1 for signal in signals if signal and signal in haystack)
    return RANKING_WEIGHTS["text_signals"] * matched / len(signals)


def freshness_score(listing: NormalizedListing, now: datetime) -> float:
    seen_at = (
        listing.raw_payload.get("first_seen_at")
        or listing.raw_payload.get("created_at")
        or listing.raw_payload.get("last_seen_at")
    )
    if seen_at is None:
        return 0.0

    age_days = max(0.0, (now - coerce_datetime(str(seen_at))).total_seconds() / 86_400)
    if age_days <= 1:
        return 10.0
    if age_days <= 3:
        return 7.0
    if age_days <= 7:
        return 4.0
    return 0.0


def dossier_alignment_score(dossier_context: Mapping[str, Any] | None) -> float:
    if not dossier_context:
        return 0.0
    readiness_score = parse_float(dossier_context.get("readiness_score")) or 0.0
    can_contact = bool(dossier_context.get("can_contact"))
    if can_contact and readiness_score >= 70:
        return RANKING_WEIGHTS["dossier_alignment"]
    if readiness_score >= 50:
        return 6.0
    return 0.0


def detect_risk_flags(
    listing: NormalizedListing,
    criteria: Mapping[str, Any],
) -> tuple[str, ...]:
    flags = list(existing_risk_flags(listing))
    haystack = listing_text(listing)

    if "charges" not in haystack and listing.raw_payload.get("charges") is None:
        flags.append("charges_non_detaillees")
    if "disponible" not in haystack and listing.raw_payload.get("available_at") is None:
        flags.append("disponibilite_non_precisee")
    if listing.raw_payload.get("address") is None:
        flags.append("adresse_imprecise")
    if listing.raw_payload.get("contact_hint") is None:
        flags.append("contact_absent")

    for avoid_keyword in criteria.get("avoid", ()):
        if avoid_keyword and avoid_keyword in haystack:
            flags.append("avoid_keyword_present")

    return tuple(dict.fromkeys(flags))


def build_reasons(
    factor_scores: Mapping[str, float],
    risk_flags: Sequence[str],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if factor_scores["budget"] > 0:
        reasons.append("Sous le budget maximum.")
    if factor_scores["surface"] > 0:
        reasons.append("Surface au dessus du minimum.")
    if factor_scores["location"] >= RANKING_WEIGHTS["location"]:
        reasons.append("Localisation compatible avec la veille.")
    elif factor_scores["location"] > 0:
        reasons.append("Ville compatible mais quartier a confirmer.")
    if factor_scores["text_signals"] > 0:
        reasons.append("Indices textuels utiles detectes.")
    if factor_scores["freshness"] > 0:
        reasons.append("Annonce recente.")
    if factor_scores["dossier_alignment"] > 0:
        reasons.append("Dossier compatible pour une prise de contact supervisee.")
    if risk_flags:
        reasons.append("Drapeaux de risque a verifier avant contact.")
    return tuple(reasons)


def existing_risk_flags(listing: NormalizedListing) -> tuple[str, ...]:
    raw = listing.raw_payload.get("risk_flags") or listing.raw_payload.get("risk_flags_json")
    if raw is None:
        return ()
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return (raw,)
        return tuple(str(value) for value in sequence_value(parsed))
    return tuple(str(value) for value in sequence_value(raw))


def sequence_field(
    payload: Mapping[str, Any],
    key: str,
    fallback_key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None:
        value = payload.get(fallback_key)
    return tuple(str(item) for item in sequence_value(value))


def mapping_field(payload: Mapping[str, Any], key: str, fallback_key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if value is None:
        value = payload.get(fallback_key)
    if value is None:
        return {}
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def sequence_value(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
        return sequence_value(parsed)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def listing_text(listing: NormalizedListing) -> str:
    return " ".join(
        part
        for part in (
            listing.normalized_title,
            normalize_text(listing.description or ""),
            normalize_text(listing.raw_payload.get("raw_text", "") or ""),
        )
        if part
    )


def coerce_listing(value: NormalizedListing | Mapping[str, Any]) -> NormalizedListing:
    if isinstance(value, NormalizedListing):
        return value
    return normalize_listing(value)


def fit_level(score: float) -> FitLevel:
    if score >= 80:
        return "strong"
    if score >= 50:
        return "medium"
    return "low"


def clamp_score(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)


def coerce_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

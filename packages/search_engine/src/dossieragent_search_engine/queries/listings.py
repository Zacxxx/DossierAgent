from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_listing_search_query(
    *,
    user_id: str,
    filters: Mapping[str, Any],
    limit: int,
    offset: int,
) -> dict[str, Any]:
    filter_clauses: list[dict[str, Any]] = [{"term": {"user_id": user_id}}]
    must_clauses: list[dict[str, Any]] = []

    for field_name in ("status", "city", "district", "watch_id"):
        value = clean_string(filters.get(field_name))
        if value is not None:
            filter_clauses.append({"term": {field_name: value}})

    q = clean_string(filters.get("q"))
    if q is not None:
        must_clauses.append(
            {
                "multi_match": {
                    "query": q,
                    "fields": ["title^3", "description", "agency_name"],
                    "type": "best_fields",
                }
            }
        )

    range_filters = {
        "price": range_body(gte=filters.get("min_price"), lte=filters.get("max_price")),
        "surface": range_body(gte=filters.get("min_surface")),
        "fit_score": range_body(gte=filters.get("min_score")),
    }
    for field_name, range_filter in range_filters.items():
        if range_filter:
            filter_clauses.append({"range": {field_name: range_filter}})

    query: dict[str, Any]
    if must_clauses or filter_clauses:
        query = {
            "bool": {
                "filter": filter_clauses,
                "must": must_clauses or [{"match_all": {}}],
            }
        }
    else:
        query = {"match_all": {}}

    return {
        "from": offset,
        "size": limit,
        "track_total_hits": True,
        "query": query,
        "sort": [
            {"fit_score": {"order": "desc", "missing": "_last"}},
            {"first_seen_at": {"order": "desc"}},
            {"listing_id": {"order": "asc"}},
        ],
    }


def range_body(*, gte: Any = None, lte: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if gte is not None:
        body["gte"] = gte
    if lte is not None:
        body["lte"] = lte
    return body


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None

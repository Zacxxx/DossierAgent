from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

LISTING_INDEX_FIELDS = (
    "listing_id",
    "user_id",
    "watch_id",
    "source",
    "source_url",
    "canonical_url",
    "canonical_url_hash",
    "source_listing_id",
    "composite_fingerprint",
    "title",
    "description",
    "city",
    "district",
    "postal_code",
    "agency_name",
    "price",
    "surface",
    "rooms",
    "status",
    "fit_score",
    "first_seen_at",
    "last_seen_at",
    "risk_flags",
)


class ElasticsearchBulkClient(Protocol):
    def bulk(self, *, operations: Sequence[Mapping[str, Any]], refresh: bool = False) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class BulkIndexResult:
    index: str
    attempted: int
    indexed: int
    errors: tuple[dict[str, Any], ...] = ()

    @property
    def status(self) -> str:
        if self.attempted == 0:
            return "skipped"
        return "indexed" if not self.errors else "partial_failed"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = list(self.errors)
        payload["status"] = self.status
        return payload


def listing_index_document(row: Mapping[str, Any]) -> dict[str, Any]:
    document = {
        "listing_id": string_value(row.get("listing_id") or row.get("id")),
        "user_id": row.get("user_id"),
        "watch_id": row.get("watch_id"),
        "source": row.get("source"),
        "source_url": row.get("source_url"),
        "canonical_url": row.get("canonical_url"),
        "canonical_url_hash": row.get("canonical_url_hash"),
        "source_listing_id": row.get("source_listing_id"),
        "composite_fingerprint": row.get("composite_fingerprint"),
        "title": row.get("title"),
        "description": row.get("description"),
        "city": row.get("city"),
        "district": row.get("district"),
        "postal_code": row.get("postal_code"),
        "agency_name": row.get("agency_name"),
        "price": row.get("price"),
        "surface": row.get("surface"),
        "rooms": row.get("rooms"),
        "status": row.get("status"),
        "fit_score": row.get("fit_score"),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
        "risk_flags": list_field(row.get("risk_flags_json"), row.get("risk_flags")),
    }
    return {field_name: document.get(field_name) for field_name in LISTING_INDEX_FIELDS}


def build_listing_bulk_operations(
    *,
    index_name: str,
    listings: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    operations: list[dict[str, Any]] = []
    for listing in listings:
        document = listing_index_document(listing)
        listing_id = document["listing_id"]
        if listing_id is None:
            raise ValueError("Listing document requires listing_id or id.")
        operations.append({"index": {"_index": index_name, "_id": listing_id}})
        operations.append(document)
    return tuple(operations)


def build_listing_bulk_ndjson(
    *,
    index_name: str,
    listings: Sequence[Mapping[str, Any]],
) -> bytes:
    operations = build_listing_bulk_operations(index_name=index_name, listings=listings)
    if not operations:
        return b""
    lines = (json.dumps(operation, ensure_ascii=True, separators=(",", ":")) for operation in operations)
    return ("\n".join(lines) + "\n").encode("utf-8")


def bulk_index_listings(
    client: ElasticsearchBulkClient,
    *,
    index_name: str,
    listings: Sequence[Mapping[str, Any]],
    refresh: bool = False,
) -> BulkIndexResult:
    operations = build_listing_bulk_operations(index_name=index_name, listings=listings)
    if not operations:
        return BulkIndexResult(index=index_name, attempted=0, indexed=0)
    payload = client.bulk(operations=operations, refresh=refresh)
    return parse_bulk_index_response(index_name=index_name, attempted=len(operations) // 2, payload=payload)


def parse_bulk_index_response(
    *,
    index_name: str,
    attempted: int,
    payload: Mapping[str, Any],
) -> BulkIndexResult:
    indexed = 0
    errors: list[dict[str, Any]] = []
    items = payload.get("items") if isinstance(payload, Mapping) else None
    if not isinstance(items, list):
        return BulkIndexResult(
            index=index_name,
            attempted=attempted,
            indexed=0,
            errors=({"error": "invalid_bulk_response"},),
        )

    for item in items:
        if not isinstance(item, Mapping):
            errors.append({"error": "invalid_bulk_item"})
            continue
        operation = item.get("index") or item.get("create") or item.get("update")
        if not isinstance(operation, Mapping):
            errors.append({"error": "missing_bulk_operation"})
            continue
        status = int(operation.get("status", 500))
        if status < 300:
            indexed += 1
            continue
        errors.append(
            {
                "listing_id": operation.get("_id"),
                "status": status,
                "error": operation.get("error", "bulk_item_failed"),
            }
        )

    return BulkIndexResult(
        index=index_name,
        attempted=attempted,
        indexed=indexed,
        errors=tuple(errors),
    )


def string_value(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def list_field(*values: Any) -> list[str]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = [value]
            value = parsed
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
            return [str(item) for item in value if item is not None]
    return []

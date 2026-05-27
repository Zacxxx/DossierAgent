from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

DEFAULT_VECTOR_DIMS = 768
LISTINGS_INDEX = "listings_v1"
DOCUMENTS_INDEX = "documents_v1"
INDEX_NAMES = (LISTINGS_INDEX, DOCUMENTS_INDEX)


class ElasticsearchIndicesClient(Protocol):
    def exists(self, *, index: str) -> bool: ...

    def create(self, *, index: str, body: Mapping[str, Any]) -> Any: ...

    def get_mapping(self, *, index: str) -> Mapping[str, Any]: ...


class ElasticsearchClient(Protocol):
    indices: ElasticsearchIndicesClient


@dataclass(frozen=True, slots=True)
class IndexBootstrapResult:
    index: str
    status: str


class IndexMappingMismatch(ValueError):
    pass


def ensure_indices(client: ElasticsearchClient) -> tuple[IndexBootstrapResult, ...]:
    results: list[IndexBootstrapResult] = []
    for index_name in INDEX_NAMES:
        expected_mapping = load_mapping(index_name)
        if client.indices.exists(index=index_name):
            current_mapping = client.indices.get_mapping(index=index_name)
            verify_index_mapping(index_name, current_mapping, expected_mapping)
            results.append(IndexBootstrapResult(index=index_name, status="verified"))
            continue

        client.indices.create(index=index_name, body=expected_mapping)
        results.append(IndexBootstrapResult(index=index_name, status="created"))

    return tuple(results)


def load_mapping(index_name: str) -> dict[str, Any]:
    if index_name not in INDEX_NAMES:
        raise KeyError(f"Unknown search index: {index_name}")

    path = mappings_directory() / f"{index_name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def verify_index_mapping(
    index_name: str,
    current_mapping: Mapping[str, Any],
    expected_mapping: Mapping[str, Any] | None = None,
) -> None:
    expected = expected_mapping or load_mapping(index_name)
    expected_properties = extract_properties(expected, index_name)
    current_properties = extract_properties(current_mapping, index_name)

    for field_name, expected_field in expected_properties.items():
        current_field = current_properties.get(field_name)
        if current_field is None:
            raise IndexMappingMismatch(f"{index_name}.{field_name} is missing.")

        for key, expected_value in expected_field.items():
            if current_field.get(key) != expected_value:
                raise IndexMappingMismatch(
                    f"{index_name}.{field_name}.{key} expected {expected_value!r}, "
                    f"got {current_field.get(key)!r}."
                )


def extract_properties(mapping: Mapping[str, Any], index_name: str) -> Mapping[str, Mapping[str, Any]]:
    current: Mapping[str, Any] = mapping
    if index_name in current:
        current = as_mapping(current[index_name])
    if "mappings" in current:
        current = as_mapping(current["mappings"])

    properties = current.get("properties")
    if not isinstance(properties, Mapping):
        raise IndexMappingMismatch(f"{index_name} mapping does not contain properties.")

    return {
        str(field_name): as_mapping(field_mapping)
        for field_name, field_mapping in properties.items()
    }


def mappings_directory() -> Path:
    return Path(__file__).resolve().parents[3] / "mappings"


def as_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"Expected mapping, got {type(value).__name__}.")
    return value

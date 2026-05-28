from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


class UnknownSourceError(KeyError):
    def __init__(self, source: str) -> None:
        super().__init__(source)
        self.source = source

    def __str__(self) -> str:
        return f"Unknown browser source adapter: {self.source}"


@dataclass(frozen=True, slots=True)
class SourceAdapter:
    source: str
    allowed_hosts: tuple[str, ...] = ()
    list_url_keys: tuple[str, ...] = ("url", "list_url", "search_url")

    def list_url(self, criteria: Mapping[str, Any]) -> str:
        for key in self.list_url_keys:
            value = criteria.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        raise ValueError(f"Source adapter {self.source} requires a list URL in criteria.")

    def accepts_url(self, url: str) -> bool:
        if not self.allowed_hosts:
            return True
        host = (urlsplit(url).hostname or "").lower()
        return host in self.allowed_hosts

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "allowed_hosts": list(self.allowed_hosts),
            "list_url_keys": list(self.list_url_keys),
        }


@dataclass(frozen=True, slots=True)
class AdapterRegistry:
    adapters: Mapping[str, SourceAdapter]

    def get(self, source: str) -> SourceAdapter:
        try:
            return self.adapters[source]
        except KeyError as exc:
            raise UnknownSourceError(source) from exc

    def as_dict(self) -> dict[str, Any]:
        return {source: adapter.as_dict() for source, adapter in self.adapters.items()}


def default_adapter_registry() -> AdapterRegistry:
    return AdapterRegistry(
        {
            "manual_url": SourceAdapter(source="manual_url"),
            "demo_seed": SourceAdapter(
                source="demo_seed",
                allowed_hosts=("demo.example", "demo.dossieragent.local"),
            ),
        }
    )

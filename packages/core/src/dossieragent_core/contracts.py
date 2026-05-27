from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PackageManifest:
    name: str
    concern: str
    owns: tuple[str, ...] = ()
    exposes: tuple[str, ...] = ()
    events: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PackageManifest":
        return cls(
            name=str(data["name"]),
            concern=str(data["concern"]),
            owns=tuple(str(item) for item in data.get("owns", ())),
            exposes=tuple(str(item) for item in data.get("exposes", ())),
            events=tuple(str(item) for item in data.get("events", ())),
        )


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    package_name: str
    description: str
    handler: Callable[..., Any] | None = field(default=None, repr=False, compare=False)


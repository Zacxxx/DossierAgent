from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .contracts import Capability, PackageManifest


class PackageRegistry:
    def __init__(self) -> None:
        self._packages: dict[str, PackageManifest] = {}
        self._capabilities: dict[str, Capability] = {}

    def register_manifest(
        self,
        manifest: PackageManifest | Mapping[str, Any],
    ) -> PackageManifest:
        package_manifest = (
            manifest if isinstance(manifest, PackageManifest) else PackageManifest.from_mapping(manifest)
        )
        if package_manifest.name in self._packages:
            raise ValueError(f"Package already registered: {package_manifest.name}")
        self._packages[package_manifest.name] = package_manifest
        return package_manifest

    def register_capability(
        self,
        package_name: str,
        capability_name: str,
        description: str,
        handler: Callable[..., Any] | None = None,
    ) -> Capability:
        if package_name not in self._packages:
            raise KeyError(f"Unknown package: {package_name}")
        if capability_name in self._capabilities:
            raise ValueError(f"Capability already registered: {capability_name}")
        capability = Capability(
            name=capability_name,
            package_name=package_name,
            description=description,
            handler=handler,
        )
        self._capabilities[capability_name] = capability
        return capability

    def packages(self) -> tuple[PackageManifest, ...]:
        return tuple(self._packages.values())

    def capabilities(self) -> tuple[Capability, ...]:
        return tuple(self._capabilities.values())

    def get_package(self, package_name: str) -> PackageManifest:
        return self._packages[package_name]

    def get_capability(self, capability_name: str) -> Capability:
        return self._capabilities[capability_name]

    def call(self, capability_name: str, **payload: Any) -> Any:
        capability = self.get_capability(capability_name)
        if capability.handler is None:
            raise LookupError(f"Capability has no handler: {capability_name}")
        return capability.handler(**payload)


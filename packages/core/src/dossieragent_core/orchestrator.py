from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .contracts import PackageManifest
from .registry import PackageRegistry


class DossierAgentCore:
    def __init__(self, registry: PackageRegistry | None = None) -> None:
        self.registry = registry or PackageRegistry()

    def install(
        self,
        manifest: PackageManifest | Mapping[str, Any],
        capabilities: Iterable[tuple[str, str, Callable[..., Any] | None]] = (),
    ) -> PackageManifest:
        package_manifest = self.registry.register_manifest(manifest)
        for capability_name, description, handler in capabilities:
            self.registry.register_capability(
                package_manifest.name,
                capability_name,
                description,
                handler,
            )
        return package_manifest

    def run(self, capability_name: str, **payload: Any) -> Any:
        return self.registry.call(capability_name, **payload)


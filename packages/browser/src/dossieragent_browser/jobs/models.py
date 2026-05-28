from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from uuid import uuid4

BrowserJobMode = Literal["direct_url", "list_page"]

SUPPORTED_MODES: set[str] = {"direct_url", "list_page"}


class BrowserJobError(ValueError):
    """Raised when a browser job payload is invalid."""


@dataclass(frozen=True, slots=True)
class BrowserJob:
    job_id: str
    source: str
    mode: BrowserJobMode
    criteria: Mapping[str, Any] = field(default_factory=dict)
    timeout: float = 30.0

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "BrowserJob":
        job_id = string_field(payload, "job_id") or f"brw_{uuid4().hex[:12]}"
        source = string_field(payload, "source") or "manual_url"
        mode = string_field(payload, "mode") or "direct_url"
        if mode not in SUPPORTED_MODES:
            raise BrowserJobError(f"Unsupported browser job mode: {mode}")

        criteria = payload.get("criteria") or {}
        if not isinstance(criteria, Mapping):
            raise BrowserJobError("Browser job criteria must be an object.")

        timeout = float(payload.get("timeout", payload.get("timeout_seconds", 30.0)))
        if timeout <= 0:
            raise BrowserJobError("Browser job timeout must be greater than zero.")

        return cls(
            job_id=job_id,
            source=source,
            mode=mode,  # type: ignore[arg-type]
            criteria=dict(criteria),
            timeout=timeout,
        )

    def direct_url(self) -> str:
        if self.mode != "direct_url":
            raise BrowserJobError(f"Job mode does not use a direct URL: {self.mode}")

        url = string_field(self.criteria, "url")
        if url is None:
            urls = self.criteria.get("urls")
            if isinstance(urls, list) and urls:
                first_url = urls[0]
                url = str(first_url).strip() if first_url is not None else None

        if not url:
            raise BrowserJobError("Direct URL browser jobs require criteria.url or criteria.urls[0].")
        return url

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["criteria"] = dict(self.criteria)
        return payload


@dataclass(frozen=True, slots=True)
class BrowserJobResult:
    job_id: str
    status: Literal["succeeded", "failed", "idle"]
    mode: str
    source: str
    candidate: Mapping[str, Any] | None = None
    error: Mapping[str, Any] | None = None
    artifacts: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifacts"] = list(self.artifacts)
        return payload


def string_field(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None

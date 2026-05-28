from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

from dossieragent_browser.jobs import BrowserJob

DEFAULT_ALLOWED_SOURCES = ("manual_url", "demo_seed")
DEFAULT_ALLOWED_SCHEMES = ("http", "https", "file")
BLOCKED_PAGE_MARKERS = (
    "captcha",
    "recaptcha",
    "connectez-vous",
    "connexion requise",
    "login required",
    "sign in to continue",
)


class ComplianceViolation(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ComplianceGuard:
    allowed_sources: tuple[str, ...] = DEFAULT_ALLOWED_SOURCES
    allowed_hosts: tuple[str, ...] = ()
    allowed_schemes: tuple[str, ...] = DEFAULT_ALLOWED_SCHEMES
    delay_seconds: float = 0.0

    @classmethod
    def from_env(cls) -> "ComplianceGuard":
        return cls(
            allowed_sources=csv_env("DOSSIERAGENT_BROWSER_ALLOWED_SOURCES")
            or DEFAULT_ALLOWED_SOURCES,
            allowed_hosts=csv_env("DOSSIERAGENT_BROWSER_ALLOWED_HOSTS"),
            allowed_schemes=csv_env("DOSSIERAGENT_BROWSER_ALLOWED_SCHEMES")
            or DEFAULT_ALLOWED_SCHEMES,
            delay_seconds=float(os.environ.get("DOSSIERAGENT_BROWSER_DELAY_SECONDS", "0")),
        )

    def check_job(self, job: BrowserJob) -> None:
        if job.source not in self.allowed_sources:
            raise ComplianceViolation(
                "source_not_allowed",
                f"Browser source is not allowlisted: {job.source}",
            )
        if job.mode == "direct_url":
            self.check_url(job.direct_url())

    def check_url(self, url: str) -> None:
        parsed = urlsplit(url)
        scheme = (parsed.scheme or "https").lower()
        if scheme not in self.allowed_schemes:
            raise ComplianceViolation(
                "scheme_not_allowed",
                f"URL scheme is not allowlisted: {scheme}",
            )

        host = (parsed.hostname or "").lower()
        if self.allowed_hosts and host not in self.allowed_hosts:
            raise ComplianceViolation(
                "host_not_allowed",
                f"URL host is not allowlisted: {host}",
            )

    def check_page_text(self, text: str) -> None:
        normalized = text.lower()
        for marker in BLOCKED_PAGE_MARKERS:
            if marker in normalized:
                raise ComplianceViolation(
                    "blocked_flow",
                    "Page requires login or captcha; bypass is outside MVP scope.",
                )

    def before_request(self) -> None:
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)


def csv_env(name: str) -> tuple[str, ...]:
    return clean_csv(os.environ.get(name, ""))


def clean_csv(value: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = value
    return tuple(part.strip().lower() for part in parts if part and part.strip())

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit


@dataclass(frozen=True, slots=True)
class NormalizedListing:
    source: str
    source_url: str
    canonical_url: str
    canonical_url_hash: str
    source_listing_id: str | None
    title: str
    normalized_title: str
    description: str | None
    city: str | None
    district: str | None
    postal_code: str | None
    price: float | None
    currency: str
    surface: float | None
    rooms: float | None
    agency_name: str | None
    composite_fingerprint: str
    raw_payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_listing(payload: Mapping[str, Any]) -> NormalizedListing:
    source_url = required_string(payload, "source_url", fallback_key="url")
    canonical_url = canonicalize_url(optional_string(payload, "canonical_url") or source_url)
    title = required_string(payload, "title")
    normalized_title = normalize_text(title)
    price = parse_float(payload.get("price"))
    surface = parse_float(payload.get("surface"))
    rooms = parse_float(payload.get("rooms"))
    city = optional_string(payload, "city")
    district = optional_string(payload, "district")
    agency_name = optional_string(payload, "agency_name")

    return NormalizedListing(
        source=required_string(payload, "source", default="unknown"),
        source_url=source_url,
        canonical_url=canonical_url,
        canonical_url_hash=canonical_url_hash(canonical_url),
        source_listing_id=optional_string(payload, "source_listing_id"),
        title=title.strip(),
        normalized_title=normalized_title,
        description=optional_string(payload, "description"),
        city=city,
        district=district,
        postal_code=optional_string(payload, "postal_code"),
        price=price,
        currency=required_string(payload, "currency", default="EUR"),
        surface=surface,
        rooms=rooms,
        agency_name=agency_name,
        composite_fingerprint=composite_fingerprint(
            city=city,
            district=district,
            price=price,
            surface=surface,
            agency_name=agency_name,
            normalized_title=normalized_title,
        ),
        raw_payload=dict(payload),
    )


def canonicalize_url(url: str) -> str:
    stripped = url.strip()
    if not stripped:
        raise ValueError("Listing URL is required.")
    if "://" not in stripped:
        stripped = f"https://{stripped}"

    parsed = urlsplit(stripped)
    scheme = parsed.scheme.lower() or "https"
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError(f"Listing URL has no host: {url!r}")

    netloc = host
    if parsed.port is not None and not is_default_port(scheme, parsed.port):
        netloc = f"{host}:{parsed.port}"

    path = normalize_url_path(parsed.path)
    return urlunsplit((scheme, netloc, path, "", ""))


def canonical_url_hash(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()


def composite_fingerprint(
    *,
    city: str | None,
    district: str | None,
    price: float | None,
    surface: float | None,
    agency_name: str | None,
    normalized_title: str,
) -> str:
    components = (
        normalize_text(city or ""),
        normalize_text(district or ""),
        numeric_component(price),
        numeric_component(surface),
        normalize_text(agency_name or ""),
        normalized_title,
    )
    return hashlib.sha256("|".join(components).encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[a-z0-9]+", ascii_text.lower())
    return " ".join(words)


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)

    match = re.search(r"-?\d+(?:[\s,.]\d+)*", str(value))
    if match is None:
        return None

    number = match.group(0).replace(" ", "")
    if "," in number and "." in number:
        number = number.replace(".", "").replace(",", ".")
    else:
        number = number.replace(",", ".")
    return float(number)


def required_string(
    payload: Mapping[str, Any],
    key: str,
    *,
    fallback_key: str | None = None,
    default: str | None = None,
) -> str:
    value = optional_string(payload, key)
    if value is None and fallback_key is not None:
        value = optional_string(payload, fallback_key)
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"Listing field is required: {key}")
    return value


def optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def normalize_url_path(path: str) -> str:
    decoded = unquote(path or "/")
    compact = re.sub(r"/+", "/", decoded)
    if not compact.startswith("/"):
        compact = f"/{compact}"
    if len(compact) > 1:
        compact = compact.rstrip("/")
    return compact


def is_default_port(scheme: str, port: int) -> bool:
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)


def numeric_component(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}".rstrip("0").rstrip(".")

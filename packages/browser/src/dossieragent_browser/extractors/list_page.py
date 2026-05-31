from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from dossieragent_browser.adapters import AdapterRegistry, default_adapter_registry
from dossieragent_browser.extractors.detail import (
    PlaywrightHtmlLoader,
    StaticHtmlLoader,
    normalize_image_urls,
    canonicalize_url,
    parse_number,
)
from dossieragent_browser.guards import ComplianceGuard


@dataclass(frozen=True, slots=True)
class ListingUrlCandidate:
    source: str
    source_url: str
    listing_url: str
    source_listing_id: str | None
    title: str | None
    price: float | None
    currency: str
    surface: float | None
    city: str | None
    district: str | None
    raw_payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["raw_payload"] = dict(self.raw_payload)
        return payload


class ListPageExtractor:
    def __init__(
        self,
        *,
        adapter_registry: AdapterRegistry | None = None,
        compliance_guard: ComplianceGuard | None = None,
    ) -> None:
        self.adapter_registry = adapter_registry or default_adapter_registry()
        self.compliance_guard = compliance_guard or ComplianceGuard.from_env()

    def extract(
        self,
        *,
        source: str,
        criteria: Mapping[str, Any],
        timeout: float = 30.0,
        html: str | None = None,
    ) -> tuple[tuple[ListingUrlCandidate, ...], str]:
        adapter = self.adapter_registry.get(source)
        list_url = adapter.list_url(criteria)
        self.compliance_guard.check_url(list_url)
        if not adapter.accepts_url(list_url):
            raise ValueError(f"List URL is not allowed for source adapter: {source}")

        loader = StaticHtmlLoader(html) if html is not None else PlaywrightHtmlLoader()
        loaded_page = loader.load(list_url, timeout=timeout)
        self.compliance_guard.check_page_text(visible_text(loaded_page.html))
        candidates = candidates_from_html(
            loaded_page.html,
            source=source,
            source_url=loaded_page.url,
            adapter=adapter,
        )
        return candidates, loaded_page.html


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, Any]] = []
        self._active_link: dict[str, Any] | None = None
        self._skip_text_depth = 0
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_text_depth += 1
            return
        if tag == "a":
            self._active_link = {"attrs": attrs_map, "text": [], "image_urls": []}
        elif tag == "img" and self._active_link is not None:
            image_url = (
                attrs_map.get("src")
                or attrs_map.get("data-src")
                or attrs_map.get("data-lazy-src")
            )
            if image_url:
                self._active_link["image_urls"].append(image_url)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self._skip_text_depth > 0:
            self._skip_text_depth -= 1
        if tag == "a" and self._active_link is not None:
            self.links.append(self._active_link)
            self._active_link = None

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text or self._skip_text_depth > 0:
            return
        self.text_parts.append(text)
        if self._active_link is not None:
            self._active_link["text"].append(text)


def extract_listing_urls(
    source: str,
    criteria: Mapping[str, Any],
    *,
    timeout: float = 30.0,
    html: str | None = None,
    adapter_registry: AdapterRegistry | None = None,
    compliance_guard: ComplianceGuard | None = None,
) -> dict[str, Any]:
    extractor = ListPageExtractor(
        adapter_registry=adapter_registry,
        compliance_guard=compliance_guard,
    )
    candidates, _html = extractor.extract(
        source=source,
        criteria=criteria,
        timeout=timeout,
        html=html,
    )
    return {
        "source": source,
        "source_url": str(criteria.get("url") or criteria.get("list_url") or criteria.get("search_url")),
        "items": [candidate.as_dict() for candidate in candidates],
    }


def candidates_from_html(
    html: str,
    *,
    source: str,
    source_url: str,
    adapter: Any,
) -> tuple[ListingUrlCandidate, ...]:
    parser = LinkParser()
    parser.feed(html)
    parser.close()

    seen_urls: set[str] = set()
    candidates: list[ListingUrlCandidate] = []
    for link in parser.links:
        attrs = link["attrs"]
        href = attrs.get("href", "").strip()
        if not href or is_non_listing_href(href):
            continue

        listing_url = canonicalize_url(urljoin(source_url, href))
        if listing_url in seen_urls or not adapter.accepts_url(listing_url):
            continue
        seen_urls.add(listing_url)

        text = clean_text(" ".join(link["text"]))
        title = clean_text(attrs.get("data-title") or text)
        image_urls = normalize_image_urls(
            [
                attrs.get("data-image-url"),
                attrs.get("data-image"),
                link.get("image_urls", []),
            ],
            base_url=listing_url,
        )
        raw_payload = {"attrs": attrs, "anchor_text": text, "image_urls": list(image_urls)}
        candidates.append(
            ListingUrlCandidate(
                source=source,
                source_url=source_url,
                listing_url=listing_url,
                source_listing_id=clean_text(attrs.get("data-listing-id")) or listing_id_from_url(listing_url),
                title=title or None,
                price=parse_number(attrs.get("data-price")) or price_from_text(text),
                currency=clean_text(attrs.get("data-currency")) or "EUR",
                surface=parse_number(attrs.get("data-surface")) or surface_from_text(text),
                city=clean_text(attrs.get("data-city")),
                district=clean_text(attrs.get("data-district")),
                raw_payload=raw_payload,
            )
        )
    return tuple(candidates)


def visible_text(html: str) -> str:
    parser = LinkParser()
    parser.feed(html)
    parser.close()
    return " ".join(parser.text_parts)


def is_non_listing_href(href: str) -> bool:
    lowered = href.lower()
    return (
        lowered.startswith("#")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
        or lowered.startswith("javascript:")
    )


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", unescape(str(value))).strip()
    return text or None


def price_from_text(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d[\d\s,.]*)\s*(?:EUR|€|euros?)", text, flags=re.IGNORECASE)
    return parse_number(match.group(1)) if match else None


def surface_from_text(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d[\d\s,.]*)\s*(?:m2|m²)", text, flags=re.IGNORECASE)
    return parse_number(match.group(1)) if match else None


def listing_id_from_url(url: str) -> str | None:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    return parts[-1] if parts else None

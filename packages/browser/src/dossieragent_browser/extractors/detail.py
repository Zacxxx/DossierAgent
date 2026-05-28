from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

from dossieragent_browser.guards import ComplianceGuard, ComplianceViolation


class ExtractionError(RuntimeError):
    """Raised when a listing page cannot be converted into a candidate."""


class ExtractionRejected(ExtractionError):
    """Raised when a page asks for login, captcha, or another blocked flow."""


@dataclass(frozen=True, slots=True)
class LoadedPage:
    url: str
    html: str
    screenshot: bytes | None = None
    trace: bytes | None = None


class HtmlLoader(Protocol):
    def load(self, url: str, *, timeout: float) -> LoadedPage:
        """Return rendered page HTML for a URL."""


@dataclass(frozen=True, slots=True)
class StaticHtmlLoader:
    html: str

    def load(self, url: str, *, timeout: float) -> LoadedPage:
        return LoadedPage(url=url, html=self.html)


@dataclass(frozen=True, slots=True)
class ListingCandidate:
    source: str
    source_url: str
    canonical_url: str
    source_listing_id: str | None
    title: str
    description: str | None
    city: str | None
    district: str | None
    postal_code: str | None
    price: float | None
    currency: str
    surface: float | None
    rooms: float | None
    agency_name: str | None
    contact_hint: str | None
    raw_payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["raw_payload"] = dict(self.raw_payload)
        return payload


class DirectUrlExtractor:
    def __init__(self, loader: HtmlLoader | None = None) -> None:
        self.loader = loader or PlaywrightHtmlLoader()

    def extract(
        self,
        url: str,
        *,
        source: str,
        criteria: Mapping[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> tuple[ListingCandidate, LoadedPage]:
        loaded_page = self.loader.load(url, timeout=timeout)
        candidate = candidate_from_html(
            loaded_page.html,
            source=source,
            source_url=loaded_page.url,
            criteria=criteria or {},
        )
        return candidate, loaded_page


class PlaywrightHtmlLoader:
    def load(self, url: str, *, timeout: float) -> LoadedPage:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - exercised only when dependency is missing.
            raise ExtractionError(
                "Playwright is required for live URL extraction. "
                "Install package dependencies and run `playwright install chromium`."
            ) from exc

        timeout_ms = int(timeout * 1000)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = context.new_page()
            trace_path: Path | None = None
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5_000))
                html = page.content()
                screenshot = page.screenshot(full_page=True)
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as trace_file:
                    trace_path = Path(trace_file.name)
                context.tracing.stop(path=str(trace_path))
                trace = trace_path.read_bytes()
                return LoadedPage(url=page.url, html=html, screenshot=screenshot, trace=trace)
            finally:
                if trace_path is not None:
                    trace_path.unlink(missing_ok=True)
                browser.close()


class PageSummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.json_ld_blocks: list[str] = []
        self._in_title = False
        self._in_json_ld = False
        self._skip_text_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "script":
            script_type = attrs_map.get("type", "").lower()
            if "application/ld+json" in script_type:
                self._in_json_ld = True
            else:
                self._skip_text_depth += 1
        elif tag in {"style", "noscript"}:
            self._skip_text_depth += 1
        elif tag == "meta":
            key = attrs_map.get("name") or attrs_map.get("property")
            content = attrs_map.get("content")
            if key and content:
                self.meta[key.lower()] = unescape(content.strip())
        elif tag == "link":
            rel = attrs_map.get("rel", "").lower()
            href = attrs_map.get("href")
            if "canonical" in rel.split() and href:
                self.links["canonical"] = unescape(href.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_json_ld:
            self._in_json_ld = False
        elif tag in {"script", "style", "noscript"} and self._skip_text_depth > 0:
            self._skip_text_depth -= 1

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if not stripped:
            return
        if self._in_title:
            self.title_parts.append(stripped)
        elif self._in_json_ld:
            self.json_ld_blocks.append(stripped)
        elif self._skip_text_depth == 0:
            self.text_parts.append(stripped)

    @property
    def title(self) -> str | None:
        return clean_string(" ".join(self.title_parts))

    @property
    def text(self) -> str:
        return normalize_whitespace(" ".join(self.text_parts))


def extract_listing_details(
    url: str,
    *,
    source: str = "manual_url",
    criteria: Mapping[str, Any] | None = None,
    timeout: float = 30.0,
    html: str | None = None,
) -> dict[str, Any]:
    loader = StaticHtmlLoader(html) if html is not None else None
    extractor = DirectUrlExtractor(loader=loader)
    candidate, _loaded_page = extractor.extract(
        url,
        source=source,
        criteria=criteria or {},
        timeout=timeout,
    )
    return candidate.as_dict()


def candidate_from_html(
    html: str,
    *,
    source: str,
    source_url: str,
    criteria: Mapping[str, Any],
) -> ListingCandidate:
    parser = PageSummaryParser()
    parser.feed(html)
    parser.close()

    text = parser.text
    reject_blocked_flow(text)

    json_ld_records = parse_json_ld(parser.json_ld_blocks)
    primary_record = first_listing_record(json_ld_records) or {}
    offers = mapping_value(primary_record.get("offers"))
    address = mapping_value(primary_record.get("address"))
    floor_size = mapping_value(primary_record.get("floorSize"))

    title = first_clean_string(
        primary_record.get("name"),
        parser.meta.get("og:title"),
        parser.meta.get("twitter:title"),
        parser.title,
    )
    if title is None:
        raise ExtractionError("Listing title could not be extracted.")

    description = first_clean_string(
        primary_record.get("description"),
        parser.meta.get("description"),
        parser.meta.get("og:description"),
    )
    raw_canonical_url = first_clean_string(
        parser.links.get("canonical"),
        primary_record.get("url"),
    )
    canonical_url = canonicalize_url(urljoin(source_url, raw_canonical_url or source_url))
    source_listing_id = first_clean_string(
        primary_record.get("sku"),
        primary_record.get("productID"),
        primary_record.get("identifier"),
        listing_id_from_url(canonical_url),
    )

    price = parse_number(offers.get("price")) or regex_number(
        text,
        r"(\d[\d\s,.]*)\s*(?:EUR|€|euros?)",
    )
    surface = parse_number(floor_size.get("value")) or regex_number(
        text,
        r"(\d[\d\s,.]*)\s*(?:m2|m²|metres?\s*carres?)",
    )
    rooms = parse_number(primary_record.get("numberOfRooms")) or parse_rooms(text, title)
    city = first_clean_string(address.get("addressLocality"), criteria.get("city"))
    postal_code = first_clean_string(address.get("postalCode"))
    district = first_clean_string(
        address.get("addressRegion"),
        criteria.get("district"),
        regex_text(text, r"(?:quartier|secteur)\s*:?\s*([A-Za-zÀ-ÿ0-9' -]{2,40})"),
    )
    agency_name = first_clean_string(
        value_from_path(primary_record, ("seller", "name")),
        value_from_path(primary_record, ("provider", "name")),
        parser.meta.get("author"),
    )

    return ListingCandidate(
        source=source,
        source_url=source_url,
        canonical_url=canonical_url,
        source_listing_id=source_listing_id,
        title=title,
        description=description,
        city=city,
        district=district,
        postal_code=postal_code,
        price=price,
        currency=first_clean_string(offers.get("priceCurrency"), criteria.get("currency")) or "EUR",
        surface=surface,
        rooms=rooms,
        agency_name=agency_name,
        contact_hint=contact_hint(text),
        raw_payload={
            "extractor": "browser.direct_url.v1",
            "json_ld_records": len(json_ld_records),
            "meta": parser.meta,
            "text_excerpt": text[:500],
        },
    )


def reject_blocked_flow(text: str) -> None:
    try:
        ComplianceGuard().check_page_text(text)
    except ComplianceViolation as exc:
        raise ExtractionRejected(str(exc)) from exc


def parse_json_ld(blocks: list[str]) -> tuple[Mapping[str, Any], ...]:
    records: list[Mapping[str, Any]] = []
    for block in blocks:
        try:
            parsed = json.loads(unescape(block))
        except json.JSONDecodeError:
            continue
        records.extend(flatten_json_ld(parsed))
    return tuple(records)


def flatten_json_ld(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        records: list[Mapping[str, Any]] = []
        for item in value:
            records.extend(flatten_json_ld(item))
        return records
    if not isinstance(value, Mapping):
        return []
    records = [value]
    graph = value.get("@graph")
    if graph is not None:
        records.extend(flatten_json_ld(graph))
    return records


def first_listing_record(records: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any] | None:
    preferred_types = {
        "apartment",
        "house",
        "lodgingbusiness",
        "offer",
        "product",
        "residence",
    }
    for record in records:
        raw_type = record.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        normalized_types = {str(value).lower() for value in types if value is not None}
        if normalized_types & preferred_types or "offers" in record:
            return record
    return records[0] if records else None


def mapping_value(value: Any) -> Mapping[str, Any]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping):
                return item
        return {}
    return value if isinstance(value, Mapping) else {}


def value_from_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def first_clean_string(*values: Any) -> str | None:
    for value in values:
        cleaned = clean_string(value)
        if cleaned is not None:
            return cleaned
    return None


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = normalize_whitespace(str(value))
    return cleaned or None


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def parse_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
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


def regex_number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return parse_number(match.group(1)) if match else None


def regex_text(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return clean_string(match.group(1)) if match else None


def parse_rooms(text: str, title: str) -> float | None:
    return regex_number(f"{title} {text}", r"\bT\s?(\d+)\b") or regex_number(
        text,
        r"(\d+(?:[,.]\d+)?)\s*(?:pieces?|pi[eè]ces?|rooms?)",
    )


def contact_hint(text: str) -> str | None:
    if re.search(r"\b(contact|telephone|téléphone|appel|email|mail)\b", text, flags=re.IGNORECASE):
        return "contact present on page"
    return None


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if not parsed.scheme:
        parsed = urlsplit(f"https://{url.strip()}")
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    netloc = host
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}"
    path = re.sub(r"/+", "/", parsed.path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def listing_id_from_url(url: str) -> str | None:
    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[-1] if parts else None

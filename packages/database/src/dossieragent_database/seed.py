from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .connection import create_connection
from .migration_runner import run_migrations

DEMO_USER_ID = "usr_demo"
DEFAULT_STORAGE_PATH = Path("storage")


@dataclass(frozen=True, slots=True)
class SeedResult:
    database_path: str
    storage_path: str
    counts: dict[str, int]


def seed_demo_data(
    connection: sqlite3.Connection,
    *,
    storage_path: str | os.PathLike[str] = DEFAULT_STORAGE_PATH,
    reset: bool = False,
) -> SeedResult:
    run_migrations(connection)
    storage_root = Path(storage_path)
    storage_root.mkdir(parents=True, exist_ok=True)

    if reset:
        clear_demo_data(connection)

    write_demo_files(storage_root)

    for table_name, rows in seed_rows(storage_root).items():
        upsert_rows(connection, table_name, rows)

    connection.commit()
    return SeedResult(
        database_path=database_path_for(connection),
        storage_path=str(storage_root),
        counts=demo_counts(connection),
    )


def clear_demo_data(connection: sqlite3.Connection) -> None:
    for table_name in (
        "idempotency_keys",
        "agent_events",
        "user_checks",
        "notifications",
        "contact_packets",
        "dossier_snapshots",
        "dossier_documents",
        "listings",
        "agent_runs",
        "market_watches",
        "search_criteria",
        "refresh_tokens",
        "users",
    ):
        column_name = "id" if table_name == "users" else "user_id"
        connection.execute(f"DELETE FROM {table_name} WHERE {column_name} = ?", (DEMO_USER_ID,))
    connection.commit()


def seed_rows(storage_root: Path) -> dict[str, tuple[dict[str, Any], ...]]:
    now = "2026-05-27T16:00:00Z"
    latest_run_at = "2026-05-27T16:08:00Z"
    extracted_root = storage_root / "extracted_text" / "demo"

    criteria = (
        {
            "id": "crit_toulouse_t2",
            "user_id": DEMO_USER_ID,
            "mode": "rent",
            "cities_json": json_data(["Toulouse"]),
            "districts_json": json_data(["Saint-Cyprien", "Carmes", "Minimes"]),
            "budget_min": None,
            "budget_max": 850,
            "surface_min": 35,
            "rooms_min": 2,
            "languages_json": json_data(["fr"]),
            "filters_json": json_data({"must_have": ["metro"], "avoid": ["meuble obligatoire"]}),
            "created_at": now,
            "updated_at": latest_run_at,
        },
        {
            "id": "crit_bordeaux_buy",
            "user_id": DEMO_USER_ID,
            "mode": "buy",
            "cities_json": json_data(["Bordeaux"]),
            "districts_json": json_data(["Chartrons", "Bastide"]),
            "budget_min": None,
            "budget_max": 265000,
            "surface_min": 42,
            "rooms_min": 2,
            "languages_json": json_data(["fr"]),
            "filters_json": json_data({"must_have": ["tram"], "status": "paused_demo_watch"}),
            "created_at": now,
            "updated_at": now,
        },
    )

    watches = (
        {
            "id": "watch_toulouse_t2",
            "user_id": DEMO_USER_ID,
            "criteria_id": "crit_toulouse_t2",
            "name": "Toulouse T2",
            "status": "active",
            "frequency": "twice_daily",
            "next_run_at": "2026-05-27T18:30:00Z",
            "last_run_at": latest_run_at,
            "source_config_json": json_data(demo_next_scan_source_config()),
            "created_at": now,
            "updated_at": latest_run_at,
        },
        {
            "id": "watch_bordeaux_buy",
            "user_id": DEMO_USER_ID,
            "criteria_id": "crit_bordeaux_buy",
            "name": "Bordeaux achat T2",
            "status": "paused",
            "frequency": "daily",
            "next_run_at": None,
            "last_run_at": None,
            "source_config_json": json_data({"sources": ["seed_direct_urls"]}),
            "created_at": now,
            "updated_at": now,
        },
    )

    return {
        "users": (
            {
                "id": DEMO_USER_ID,
                "email": "demo@dossieragent.local",
                "password_hash": "demo-local-password-hash",
                "display_name": "Demo Locataire",
                "created_at": now,
                "updated_at": latest_run_at,
            },
        ),
        "search_criteria": criteria,
        "market_watches": watches,
        "listings": demo_listings(now, latest_run_at),
        "dossier_documents": demo_documents(now, extracted_root),
        "dossier_snapshots": demo_snapshots(latest_run_at),
        "contact_packets": demo_packets(latest_run_at),
        "user_checks": demo_checks(latest_run_at),
        "notifications": demo_notifications(latest_run_at),
        "agent_runs": demo_runs(now, latest_run_at),
        "agent_events": demo_events(now, latest_run_at),
    }


def demo_next_scan_source_config() -> dict[str, Any]:
    list_url = "https://demo.dossieragent.local/search/toulouse-t2-run"
    return {
        "sources": [
            {
                "source": "demo_seed",
                "mode": "list_page",
                "url": list_url,
                "timeout": 5,
                "html": demo_next_scan_list_page_html(list_url),
                "detail_html_by_url": demo_next_scan_detail_pages(),
            }
        ]
    }


def demo_next_scan_list_page_html(list_url: str) -> str:
    return f"""
<!doctype html>
<html>
  <head><title>Demo scan Toulouse T2</title><link rel="canonical" href="{list_url}" /></head>
  <body>
    <main>
      <a href="/listings/031"
        data-listing-id="seed-031"
        data-title="Deux pieces renove rue des Filatiers"
        data-price="805"
        data-currency="EUR"
        data-surface="41"
        data-city="Toulouse"
        data-district="Carmes"
        data-image-url="https://images.unsplash.com/photo-1560185127-6ed189bf02f4?auto=format&fit=crop&w=900&q=80">
        Deux pieces renove rue des Filatiers - 805 EUR - 41 m2
      </a>
      <a href="/listings/001"
        data-listing-id="seed-001"
        data-title="T2 Saint-Cyprien proche metro"
        data-price="790"
        data-currency="EUR"
        data-surface="39"
        data-city="Toulouse"
        data-district="Saint-Cyprien">
        T2 Saint-Cyprien proche metro - deja connu
      </a>
      <a href="/listings/repost-carmes-002"
        data-listing-id="seed-repost-002"
        data-title="T2 Carmes calme balcon"
        data-price="820"
        data-currency="EUR"
        data-surface="38"
        data-city="Toulouse"
        data-district="Carmes">
        T2 Carmes calme balcon - nouvelle URL
      </a>
    </main>
  </body>
</html>
""".strip()


def demo_next_scan_detail_pages() -> dict[str, str]:
    return {
        "https://demo.dossieragent.local/listings/031": demo_listing_detail_html(
            canonical_url="https://demo.dossieragent.local/listings/031",
            sku="seed-031",
            title="Deux pieces renove rue des Filatiers",
            description=(
                "T2 renove a Carmes, proche metro, charges incluses, disponible maintenant. "
                "Contact agence pour organiser une visite supervisee."
            ),
            image_url="https://images.unsplash.com/photo-1560185127-6ed189bf02f4?auto=format&fit=crop&w=900&q=80",
            price=805,
            surface=41,
            rooms=2,
            city="Toulouse",
            district="Carmes",
            postal_code="31000",
            seller="Agence Demo Toulouse",
        ),
        "https://demo.dossieragent.local/listings/001": demo_listing_detail_html(
            canonical_url="https://demo.dossieragent.local/listings/001",
            sku="seed-001",
            title="T2 Saint-Cyprien proche metro",
            description=(
                "T2 Saint-Cyprien proche metro, charges incluses, disponible maintenant. "
                "Contact agence pour organiser une visite supervisee."
            ),
            image_url="https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=900&q=80",
            price=790,
            surface=39,
            rooms=2,
            city="Toulouse",
            district="Saint-Cyprien",
            postal_code="31300",
            seller="Agence Demo Toulouse",
        ),
        "https://demo.dossieragent.local/listings/repost-carmes-002": demo_listing_detail_html(
            canonical_url="https://demo.dossieragent.local/listings/repost-carmes-002",
            sku="seed-repost-002",
            title="T2 Carmes calme balcon",
            description=(
                "T2 Carmes calme avec balcon, metro proche, charges incluses, "
                "disponible maintenant. Contact gestionnaire."
            ),
            image_url="https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=900&q=80",
            price=820,
            surface=38,
            rooms=2,
            city="Toulouse",
            district="Carmes",
            postal_code="31000",
            seller="Gestion Carmes Demo",
        ),
    }


def demo_listing_detail_html(
    *,
    canonical_url: str,
    sku: str,
    title: str,
    description: str,
    image_url: str,
    price: int,
    surface: int,
    rooms: int,
    city: str,
    district: str,
    postal_code: str,
    seller: str,
) -> str:
    json_ld = {
        "@context": "https://schema.org",
        "@type": "Apartment",
        "name": title,
        "description": description,
        "url": canonical_url,
        "image": [image_url],
        "sku": sku,
        "numberOfRooms": rooms,
        "floorSize": {"@type": "QuantitativeValue", "value": surface, "unitCode": "MTK"},
        "offers": {"@type": "Offer", "price": str(price), "priceCurrency": "EUR"},
        "address": {
            "@type": "PostalAddress",
            "addressLocality": city,
            "addressRegion": district,
            "postalCode": postal_code,
        },
        "seller": {"@type": "RealEstateAgent", "name": seller},
    }
    return f"""
<!doctype html>
<html>
  <head>
    <title>{title}</title>
    <link rel="canonical" href="{canonical_url}" />
    <meta name="description" content="{description}" />
    <meta property="og:image" content="{image_url}" />
    <script type="application/ld+json">{json_data(json_ld)}</script>
  </head>
  <body>
    <main>
      <h1>{title}</h1>
      <p>{description}</p>
      <p>{surface} m2 - {rooms} pieces - {price} EUR - quartier: {district}</p>
    </main>
  </body>
</html>
""".strip()


def demo_listings(now: str, latest_run_at: str) -> tuple[dict[str, Any], ...]:
    strong_matches = [
        ("lst_001", "T2 Saint-Cyprien proche metro", "Saint-Cyprien", 790, 39, 91),
        ("lst_002", "T2 Carmes calme avec balcon", "Carmes", 820, 38, 88),
        ("lst_003", "T2 Minimes lumineux ligne B", "Minimes", 760, 36, 84),
        ("lst_004", "Appartement deux pieces Patte d Oie", "Patte d Oie", 735, 37, 82),
    ]
    rows: list[dict[str, Any]] = []
    for index, (listing_id, title, district, price, surface, score) in enumerate(strong_matches, 1):
        rows.append(
            listing_row(
                listing_id,
                title,
                "recommended",
                district,
                price,
                surface,
                score,
                now,
                latest_run_at,
                risk_flags=["charges_non_detaillees"] if index == 1 else [],
                explanation=[
                    "Sous le budget maximum",
                    "Surface au dessus du minimum",
                    "Localisation compatible avec la veille",
                ],
            )
        )

    for index in range(5, 14):
        rows.append(
            listing_row(
                f"lst_{index:03}",
                f"Toulouse location candidate {index:02}",
                "new",
                ["Saint-Cyprien", "Carmes", "Minimes"][index % 3],
                700 + index * 8,
                34 + index % 6,
                60 + index % 12,
                now,
                latest_run_at,
                explanation=["Candidate a reviser"],
            )
        )

    for index in range(14, 22):
        duplicate_of = f"lst_{((index - 14) % 4) + 1:03}"
        rows.append(
            listing_row(
                f"lst_{index:03}",
                f"Duplicate exact {index:02}",
                "duplicate",
                "Saint-Cyprien",
                790,
                39,
                0,
                now,
                latest_run_at,
                duplicate_of_listing_id=duplicate_of,
                explanation=["URL canonique ou identifiant source deja vu"],
            )
        )

    for index in range(22, 26):
        duplicate_of = f"lst_{index - 21:03}"
        rows.append(
            listing_row(
                f"lst_{index:03}",
                f"Repost probable {index:02}",
                "repost",
                "Carmes",
                810 + index % 3,
                38,
                0,
                now,
                latest_run_at,
                duplicate_of_listing_id=duplicate_of,
                explanation=["Texte tres proche avec URL differente"],
            )
        )

    for index in range(26, 31):
        rows.append(
            listing_row(
                f"lst_{index:03}",
                f"Annonce hors criteres {index:02}",
                "trash",
                "Peripherie",
                920 + index,
                28 + index % 3,
                20 + index % 10,
                now,
                latest_run_at,
                risk_flags=["hors_budget", "surface_insuffisante"],
                explanation=["Hors budget ou surface insuffisante"],
            )
        )

    return tuple(rows)


def listing_row(
    listing_id: str,
    title: str,
    status: str,
    district: str,
    price: float,
    surface: float,
    score: float,
    now: str,
    latest_run_at: str,
    *,
    duplicate_of_listing_id: str | None = None,
    risk_flags: Iterable[str] = (),
    explanation: Iterable[str] = (),
) -> dict[str, Any]:
    numeric_id = listing_id.removeprefix("lst_")
    return {
        "id": listing_id,
        "user_id": DEMO_USER_ID,
        "watch_id": "watch_toulouse_t2",
        "source": "demo_seed",
        "source_url": f"https://demo.dossieragent.local/listings/{numeric_id}",
        "canonical_url": f"https://demo.dossieragent.local/listings/{numeric_id}",
        "canonical_url_hash": f"hash_{numeric_id}",
        "source_listing_id": f"seed-{numeric_id}",
        "title": title,
        "description": f"{title}. Donnees injectees par le seed local DossierAgent.",
        "city": "Toulouse",
        "district": district,
        "postal_code": "31000",
        "price": price,
        "currency": "EUR",
        "surface": surface,
        "rooms": 2,
        "agency_name": "Agence Demo Toulouse",
        "contact_hint": "contact manuel uniquement",
        "composite_fingerprint": f"fp_{district.lower().replace(' ', '_')}_{price}_{surface}",
        "duplicate_of_listing_id": duplicate_of_listing_id,
        "status": status,
        "fit_score": score,
        "fit_level": "strong" if score >= 80 else "medium" if score >= 50 else "low",
        "risk_flags_json": json_data(list(risk_flags)),
        "explanation_json": json_data(list(explanation)),
        "raw_payload_json": json_data(
            {
                "seed": True,
                "source": "demo_seed",
                "image_urls": demo_listing_images(numeric_id),
            }
        ),
        "first_seen_at": now,
        "last_seen_at": latest_run_at,
        "created_at": now,
        "updated_at": latest_run_at,
    }


def demo_listing_images(numeric_id: str) -> list[str]:
    image_by_listing = {
        "001": "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=900&q=80",
        "002": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=900&q=80",
        "003": "https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=900&q=80",
        "004": "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=900&q=80",
    }
    return [image_by_listing[numeric_id]] if numeric_id in image_by_listing else []


def demo_documents(now: str, extracted_root: Path) -> tuple[dict[str, Any], ...]:
    return (
        document_row("doc_identity", "cni.pdf", "identity", "identity", "user", "valid", 2, now, extracted_root),
        document_row("doc_payslip_march", "fiche_paie_mars.pdf", "payslip", "payslip", "user", "valid", 1, now, extracted_root),
        document_row("doc_payslip_april", "fiche_paie_avril.pdf", "payslip", "payslip", "user", "valid", 1, now, extracted_root),
        document_row("doc_payslip_may", "fiche_paie_mai.pdf", "payslip", "payslip", "user", "valid", 1, now, extracted_root),
        document_row(
            "doc_tax_notice",
            "avis_impot_2023.pdf",
            "tax_notice",
            "tax_notice",
            "user",
            "needs_review",
            3,
            now,
            extracted_root,
            warnings=["Avis fiscal possiblement obsolete"],
        ),
        document_row(
            "doc_employment_contract_missing",
            "contrat_travail_a_fournir.pdf",
            "employment_contract",
            None,
            "user",
            "needs_review",
            0,
            now,
            extracted_root,
            issues=["Piece manquante dans le dossier de demo"],
        ),
    )


def document_row(
    document_id: str,
    filename: str,
    declared_type: str,
    detected_type: str | None,
    detected_owner_type: str,
    status: str,
    page_count: int,
    now: str,
    extracted_root: Path,
    *,
    issues: Iterable[str] = (),
    warnings: Iterable[str] = (),
) -> dict[str, Any]:
    extracted_text_path = extracted_root / f"{document_id}.txt"
    return {
        "id": document_id,
        "user_id": DEMO_USER_ID,
        "filename": filename,
        "storage_path": f"storage/documents/demo/{filename}",
        "mime_type": "application/pdf",
        "file_size": 1024 + len(filename),
        "sha256": f"seed-sha256-{document_id}",
        "declared_type": declared_type,
        "detected_type": detected_type,
        "detected_owner_type": detected_owner_type,
        "page_count": page_count,
        "status": status,
        "extracted_text_path": str(extracted_text_path),
        "issues_json": json_data(list(issues)),
        "warnings_json": json_data(list(warnings)),
        "created_at": now,
        "updated_at": now,
    }


def demo_snapshots(latest_run_at: str) -> tuple[dict[str, Any], ...]:
    return (
        {
            "id": "snap_demo_latest",
            "user_id": DEMO_USER_ID,
            "readiness_score": 78,
            "can_contact": 1,
            "can_send_full_dossier": 0,
            "missing_documents_json": json_data(
                [
                    {
                        "type": "employment_contract",
                        "severity": "high",
                        "reason": "Piece absente",
                    },
                    {
                        "type": "latest_tax_notice",
                        "severity": "medium",
                        "reason": "Avis d impot possiblement obsolete",
                    },
                ]
            ),
            "valid_documents_json": json_data(
                ["doc_identity", "doc_payslip_march", "doc_payslip_april", "doc_payslip_may"]
            ),
            "warnings_json": json_data(["Avis d impot possiblement obsolete."]),
            "recommendations_json": json_data(
                [
                    "Ajouter le contrat de travail",
                    "Remplacer l avis fiscal par la version la plus recente",
                ]
            ),
            "created_at": latest_run_at,
        },
    )


def demo_packets(latest_run_at: str) -> tuple[dict[str, Any], ...]:
    return (
        {
            "id": "pkt_001",
            "user_id": DEMO_USER_ID,
            "listing_id": "lst_001",
            "language": "fr",
            "tone": "polite_direct",
            "status": "ready_for_review",
            "message_draft": (
                "Bonjour, je vous contacte au sujet du T2 a Saint-Cyprien. "
                "Je suis interesse par une visite cette semaine."
            ),
            "questions_json": json_data(
                [
                    "Les charges sont elles incluses ?",
                    "Une visite est elle possible cette semaine ?",
                ]
            ),
            "dossier_summary_json": json_data(
                {
                    "can_contact": True,
                    "can_send_full_dossier": False,
                    "missing_documents": ["employment_contract"],
                }
            ),
            "used_at": None,
            "used_channel": None,
            "created_at": latest_run_at,
            "updated_at": latest_run_at,
        },
        {
            "id": "pkt_002",
            "user_id": DEMO_USER_ID,
            "listing_id": "lst_002",
            "language": "fr",
            "tone": "polite_direct",
            "status": "ready_for_review",
            "message_draft": (
                "Bonjour, votre annonce pour le T2 aux Carmes m interesse. "
                "Pouvez vous confirmer la disponibilite du logement ?"
            ),
            "questions_json": json_data(["La disponibilite est elle immediate ?", "Le balcon est il privatif ?"]),
            "dossier_summary_json": json_data(
                {
                    "can_contact": True,
                    "can_send_full_dossier": False,
                    "missing_documents": ["latest_tax_notice"],
                }
            ),
            "used_at": None,
            "used_channel": None,
            "created_at": latest_run_at,
            "updated_at": latest_run_at,
        },
    )


def demo_checks(latest_run_at: str) -> tuple[dict[str, Any], ...]:
    return (
        check_row("chk_packet_001", "contact_packet", "pkt_001", "Relire le paquet Saint-Cyprien", latest_run_at),
        check_row("chk_packet_002", "contact_packet", "pkt_002", "Relire le paquet Carmes", latest_run_at),
        check_row("chk_tax_notice", "dossier_document", "doc_tax_notice", "Verifier l avis fiscal", latest_run_at),
    )


def check_row(check_id: str, resource_type: str, resource_id: str, title: str, now: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "user_id": DEMO_USER_ID,
        "type": "manual_review",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "title": title,
        "summary": "Validation humaine requise avant action.",
        "status": "pending",
        "payload_json": json_data({"seed": True}),
        "completed_with": None,
        "completed_note": None,
        "created_at": now,
        "completed_at": None,
    }


def demo_notifications(latest_run_at: str) -> tuple[dict[str, Any], ...]:
    notifications = [
        ("ntf_001", "new_listing", "2 fortes recommandations", "Deux annonces depassent le seuil fort.", "agent_run", "run_latest"),
        ("ntf_002", "run_completed", "Scan termine", "24 candidats, 8 doublons, 4 reposts.", "agent_run", "run_latest"),
        ("ntf_003", "dossier_warning", "Dossier incomplet", "Contrat de travail manquant.", "dossier_snapshot", "snap_demo_latest"),
        ("ntf_004", "packet_ready", "Paquet pret", "Le paquet Saint-Cyprien attend validation.", "contact_packet", "pkt_001"),
        ("ntf_005", "document_review", "Document a verifier", "Avis fiscal possiblement obsolete.", "dossier_document", "doc_tax_notice"),
    ]
    return tuple(
        {
            "id": notification_id,
            "user_id": DEMO_USER_ID,
            "type": notification_type,
            "title": title,
            "body": body,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "read_at": None,
            "created_at": latest_run_at,
        }
        for notification_id, notification_type, title, body, resource_type, resource_id in notifications
    )


def demo_runs(now: str, latest_run_at: str) -> tuple[dict[str, Any], ...]:
    return (
        {
            "id": "run_previous",
            "user_id": DEMO_USER_ID,
            "watch_id": "watch_toulouse_t2",
            "trigger_type": "cron",
            "intent": "run_market_watch",
            "status": "completed",
            "current_step": "completed",
            "summary_json": json_data({"scanned": 30, "duplicates": 6, "reposts": 2, "new": 4, "strong_matches": 1}),
            "error_json": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": now,
        },
        {
            "id": "run_latest",
            "user_id": DEMO_USER_ID,
            "watch_id": "watch_toulouse_t2",
            "trigger_type": "manual",
            "intent": "run_market_watch",
            "status": "completed",
            "current_step": "completed",
            "summary_json": json_data({"scanned": 42, "duplicates": 8, "reposts": 4, "new": 5, "strong_matches": 2}),
            "error_json": None,
            "created_at": "2026-05-27T16:02:00Z",
            "updated_at": latest_run_at,
            "completed_at": latest_run_at,
        },
    )


def demo_events(now: str, latest_run_at: str) -> tuple[dict[str, Any], ...]:
    latest_events = [
        ("evt_latest_001", "run_started", "info", "Scan demarre", "2026-05-27T16:02:00Z", {"watch_id": "watch_toulouse_t2"}),
        ("evt_latest_002", "browser_extract", "info", "24 candidats bruts lus", "2026-05-27T16:03:00Z", {"candidates": 24}),
        ("evt_latest_003", "dedupe", "info", "8 doublons exacts ignores", "2026-05-27T16:04:00Z", {"duplicates": 8}),
        ("evt_latest_004", "dedupe", "info", "4 reposts marques", "2026-05-27T16:05:00Z", {"reposts": 4}),
        ("evt_latest_005", "ranking", "info", "4 nouvelles annonces interessantes", "2026-05-27T16:06:00Z", {"recommended": 4}),
        ("evt_latest_006", "checks", "warning", "3 validations en attente", "2026-05-27T16:07:00Z", {"checks": 3}),
        ("evt_latest_007", "run_completed", "info", "Scan termine", latest_run_at, {"status": "completed"}),
    ]
    previous_events = [
        ("evt_previous_001", "run_started", "info", "Scan cron demarre", now, {"watch_id": "watch_toulouse_t2"}),
        ("evt_previous_002", "ranking", "info", "1 forte recommandation", now, {"recommended": 1}),
        ("evt_previous_003", "run_completed", "info", "Scan cron termine", now, {"status": "completed"}),
    ]
    return tuple(
        {
            "id": event_id,
            "run_id": "run_latest" if event_id.startswith("evt_latest") else "run_previous",
            "user_id": DEMO_USER_ID,
            "type": event_type,
            "severity": severity,
            "message": message,
            "payload_json": json_data(payload),
            "created_at": created_at,
        }
        for event_id, event_type, severity, message, created_at, payload in latest_events + previous_events
    )


def write_demo_files(storage_root: Path) -> None:
    extracted_root = storage_root / "extracted_text" / "demo"
    extracted_root.mkdir(parents=True, exist_ok=True)
    for document_id, text in {
        "doc_identity": "Carte nationale d identite. Nom: Demo Locataire. Document valide.",
        "doc_payslip_march": "Fiche de paie mars 2026. Employeur: Demo SAS. Salaire net: 2450 EUR.",
        "doc_payslip_april": "Fiche de paie avril 2026. Employeur: Demo SAS. Salaire net: 2450 EUR.",
        "doc_payslip_may": "Fiche de paie mai 2026. Employeur: Demo SAS. Salaire net: 2450 EUR.",
        "doc_tax_notice": "Avis d impot 2023. Document possiblement obsolete pour le dossier courant.",
        "doc_employment_contract_missing": "Document attendu mais non fourni dans le seed de demonstration.",
    }.items():
        (extracted_root / f"{document_id}.txt").write_text(text + "\n", encoding="utf-8")


def upsert_rows(
    connection: sqlite3.Connection,
    table_name: str,
    rows: Iterable[Mapping[str, Any]],
) -> None:
    for row in rows:
        columns = tuple(row.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        update_sql = ", ".join(f"{column} = excluded.{column}" for column in columns if column != "id")
        values = tuple(row[column] for column in columns)
        connection.execute(
            f"""
            INSERT INTO {table_name} ({column_sql})
            VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET {update_sql}
            """,
            values,
        )


def demo_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "users",
        "search_criteria",
        "market_watches",
        "listings",
        "dossier_documents",
        "dossier_snapshots",
        "contact_packets",
        "user_checks",
        "notifications",
        "agent_runs",
        "agent_events",
    )
    return {table: count_rows(connection, table) for table in tables}


def count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    column_name = "id" if table_name == "users" else "user_id"
    row = connection.execute(
        f"SELECT COUNT(*) AS count FROM {table_name} WHERE {column_name} = ?",
        (DEMO_USER_ID,),
    ).fetchone()
    return int(row["count"])


def database_path_for(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA database_list").fetchone()
    return str(row["file"]) if row is not None else ""


def json_data(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed deterministic DossierAgent demo data.")
    parser.add_argument("--database-path", "--db", default=None)
    parser.add_argument("--storage-path", default=str(DEFAULT_STORAGE_PATH))
    parser.add_argument("--reset", action="store_true", help="Delete existing demo rows before seeding.")
    args = parser.parse_args()

    connection = create_connection(args.database_path)
    try:
        result = seed_demo_data(connection, storage_path=args.storage_path, reset=args.reset)
    finally:
        connection.close()

    print(json.dumps({"seeded": True, **asdict(result)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

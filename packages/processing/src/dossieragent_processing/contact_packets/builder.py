from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContactPacketDraft:
    message_draft: str
    questions_to_ask: tuple[str, ...]
    dossier_summary: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "message_draft": self.message_draft,
            "questions_to_ask": list(self.questions_to_ask),
            "dossier_summary": dict(self.dossier_summary),
        }


def build_contact_packet(
    listing: Mapping[str, Any],
    *,
    dossier_summary: Mapping[str, Any] | None = None,
    language: str = "fr",
    tone: str = "polite_direct",
    include_dossier_summary: bool = True,
) -> ContactPacketDraft:
    if language != "fr":
        raise ValueError("Only French contact packets are implemented for the MVP.")
    if tone != "polite_direct":
        raise ValueError("Only polite_direct tone is implemented for the MVP.")

    summary = normalize_dossier_summary(dossier_summary) if include_dossier_summary else {}
    return ContactPacketDraft(
        message_draft=build_message(listing, summary),
        questions_to_ask=build_questions(listing),
        dossier_summary=summary,
    )


def build_message(listing: Mapping[str, Any], dossier_summary: Mapping[str, Any]) -> str:
    title = clean_text(listing.get("title")) or "votre annonce"
    city = clean_text(listing.get("city"))
    district = clean_text(listing.get("district"))
    location = ", ".join(part for part in (district, city) if part)
    subject = f"{title} a {location}" if location else title

    sentences = [
        f"Bonjour, je vous contacte au sujet de {subject}.",
        "Le logement correspond a ma recherche et je souhaite savoir s il est toujours disponible.",
    ]

    if dossier_summary.get("can_contact"):
        sentences.append("Je peux partager les elements utiles du dossier apres validation manuelle.")
    else:
        sentences.append("Je souhaite d abord confirmer les informations cles avant toute transmission de dossier.")

    sentences.append("Serait il possible d organiser une visite ou un premier echange cette semaine ?")
    return " ".join(sentences)


def build_questions(listing: Mapping[str, Any]) -> tuple[str, ...]:
    risk_flags = set(sequence_value(listing.get("risk_flags") or listing.get("risk_flags_json")))
    questions: list[str] = []
    if "charges_non_detaillees" in risk_flags:
        questions.append("Les charges sont elles incluses et detaillees ?")
    if "disponibilite_non_precisee" in risk_flags:
        questions.append("Quelle est la date de disponibilite du logement ?")
    if "adresse_imprecise" in risk_flags:
        questions.append("Pouvez vous confirmer la localisation approximative avant la visite ?")
    if "contact_absent" in risk_flags:
        questions.append("Quel est le meilleur canal pour convenir d une visite ?")

    if not questions:
        questions.extend(
            [
                "Le logement est il toujours disponible ?",
                "Une visite est elle possible cette semaine ?",
            ]
        )
    return tuple(questions[:4])


def normalize_dossier_summary(dossier_summary: Mapping[str, Any] | None) -> dict[str, Any]:
    if not dossier_summary:
        return {
            "can_contact": False,
            "can_send_full_dossier": False,
            "missing_documents": [],
        }
    return {
        "can_contact": bool(dossier_summary.get("can_contact")),
        "can_send_full_dossier": bool(dossier_summary.get("can_send_full_dossier")),
        "missing_documents": list(sequence_value(dossier_summary.get("missing_documents"))),
        "readiness_score": dossier_summary.get("readiness_score"),
    }


def clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def sequence_value(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
        return sequence_value(parsed)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)

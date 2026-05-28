from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


READINESS_WEIGHTS: dict[str, float] = {
    "identity": 30.0,
    "recent_income": 30.0,
    "employment": 20.0,
    "fiscality": 10.0,
    "coherence_freshness": 10.0,
}

USABLE_STATUSES = {"uploaded", "classified", "valid"}
STALE_TAX_MARKERS = ("obsolete", "ancien", "2023", "expire", "perime")


@dataclass(frozen=True, slots=True)
class MissingDocument:
    type: str
    severity: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DossierReadinessResult:
    readiness_score: float
    can_contact: bool
    can_send_full_dossier: bool
    missing_documents: tuple[MissingDocument, ...]
    valid_documents: tuple[str, ...]
    warnings: tuple[str, ...]
    recommendations: tuple[str, ...]
    factor_scores: Mapping[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "readiness_score": self.readiness_score,
            "can_contact": self.can_contact,
            "can_send_full_dossier": self.can_send_full_dossier,
            "missing_documents": [document.as_dict() for document in self.missing_documents],
            "valid_documents": list(self.valid_documents),
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
            "factor_scores": dict(self.factor_scores),
        }


def analyze_dossier(
    documents: Sequence[Mapping[str, Any]],
    *,
    now: str | datetime | None = None,
) -> DossierReadinessResult:
    del now  # Reserved for date-aware freshness rules once document dates are parsed.
    active_documents = [normalize_document(document) for document in documents if document_status(document) != "deleted"]
    usable_documents = [document for document in active_documents if is_usable_document(document)]

    identity_docs = documents_of_type(usable_documents, "identity")
    payslip_docs = documents_of_type(usable_documents, "payslip")
    employment_docs = documents_of_type(usable_documents, "employment_contract")
    tax_notice_docs = documents_of_type(active_documents, "tax_notice")
    usable_tax_docs = [document for document in tax_notice_docs if is_usable_document(document)]
    stale_tax_docs = [document for document in tax_notice_docs if is_stale_tax_notice(document)]
    problem_docs = [
        document
        for document in active_documents
        if document["status"] in {"invalid"} or (document["issues"] and document["status"] != "needs_review")
    ]

    missing: list[MissingDocument] = []
    recommendations: list[str] = []

    factor_scores = {
        "identity": READINESS_WEIGHTS["identity"] if identity_docs else 0.0,
        "recent_income": income_score(payslip_docs),
        "employment": READINESS_WEIGHTS["employment"] if employment_docs else 0.0,
        "fiscality": fiscality_score(usable_tax_docs, stale_tax_docs),
        "coherence_freshness": coherence_score(identity_docs, payslip_docs, problem_docs),
    }

    if not identity_docs:
        missing.append(MissingDocument("identity", "high", "Piece d identite absente"))
        recommendations.append("Ajouter une piece d identite lisible.")

    if len(payslip_docs) < 3:
        missing.append(
            MissingDocument(
                "recent_income",
                "high",
                "Trois justificatifs de revenus recents sont attendus",
            )
        )
        recommendations.append("Ajouter les trois derniers justificatifs de revenus.")

    if not employment_docs:
        missing.append(MissingDocument("employment_contract", "high", "Piece absente"))
        recommendations.append("Ajouter le contrat de travail.")

    if not usable_tax_docs or stale_tax_docs:
        missing.append(MissingDocument("latest_tax_notice", "medium", tax_notice_reason(stale_tax_docs)))
        recommendations.append("Remplacer l avis fiscal par la version la plus recente.")

    warnings = collect_warnings(active_documents, stale_tax_docs, problem_docs)
    score = round(sum(factor_scores.values()), 2)
    high_missing_types = {document.type for document in missing if document.severity == "high"}
    can_contact = bool(identity_docs and payslip_docs and score >= 60)
    can_send_full_dossier = score >= 90 and not high_missing_types and not stale_tax_docs and not problem_docs

    return DossierReadinessResult(
        readiness_score=score,
        can_contact=can_contact,
        can_send_full_dossier=can_send_full_dossier,
        missing_documents=tuple(missing),
        valid_documents=tuple(document["id"] for document in usable_documents if document["type"] is not None),
        warnings=tuple(dict.fromkeys(warnings)),
        recommendations=tuple(dict.fromkeys(recommendations)),
        factor_scores={key: round(value, 2) for key, value in factor_scores.items()},
    )


def normalize_document(document: Mapping[str, Any]) -> dict[str, Any]:
    issues = tuple(str(value) for value in sequence_value(document.get("issues") or document.get("issues_json")))
    warnings = tuple(str(value) for value in sequence_value(document.get("warnings") or document.get("warnings_json")))
    return {
        "id": str(document.get("id") or document.get("document_id") or ""),
        "type": clean_document_type(document.get("detected_type") or document.get("declared_type")),
        "status": document_status(document),
        "filename": str(document.get("filename") or ""),
        "issues": issues,
        "warnings": warnings,
    }


def document_status(document: Mapping[str, Any]) -> str:
    return str(document.get("status") or "").strip().lower()


def clean_document_type(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "id": "identity",
        "identity_card": "identity",
        "proof_of_income": "payslip",
        "income": "payslip",
        "latest_tax_notice": "tax_notice",
        "tax": "tax_notice",
        "work_contract": "employment_contract",
    }
    return aliases.get(normalized, normalized) if normalized else None


def is_usable_document(document: Mapping[str, Any]) -> bool:
    return bool(document["type"] and document["status"] in USABLE_STATUSES and not document["issues"])


def documents_of_type(documents: Sequence[Mapping[str, Any]], document_type: str) -> list[Mapping[str, Any]]:
    return [document for document in documents if document["type"] == document_type]


def income_score(payslip_docs: Sequence[Mapping[str, Any]]) -> float:
    count = min(3, len(payslip_docs))
    return round(READINESS_WEIGHTS["recent_income"] * count / 3, 2)


def fiscality_score(
    usable_tax_docs: Sequence[Mapping[str, Any]],
    stale_tax_docs: Sequence[Mapping[str, Any]],
) -> float:
    if stale_tax_docs:
        return 8.0
    if usable_tax_docs:
        return READINESS_WEIGHTS["fiscality"]
    return 0.0


def coherence_score(
    identity_docs: Sequence[Mapping[str, Any]],
    payslip_docs: Sequence[Mapping[str, Any]],
    problem_docs: Sequence[Mapping[str, Any]],
) -> float:
    if not identity_docs or not payslip_docs:
        return 0.0
    return max(0.0, READINESS_WEIGHTS["coherence_freshness"] - min(5.0, len(problem_docs) * 5.0))


def is_stale_tax_notice(document: Mapping[str, Any]) -> bool:
    if document["type"] != "tax_notice":
        return False
    haystack = " ".join(
        (
            document["filename"].lower(),
            " ".join(document["warnings"]).lower(),
            " ".join(document["issues"]).lower(),
            document["status"],
        )
    )
    return document["status"] == "needs_review" or any(marker in haystack for marker in STALE_TAX_MARKERS)


def tax_notice_reason(stale_tax_docs: Sequence[Mapping[str, Any]]) -> str:
    if stale_tax_docs:
        return "Avis d impot possiblement obsolete"
    return "Avis d impot absent"


def collect_warnings(
    documents: Sequence[Mapping[str, Any]],
    stale_tax_docs: Sequence[Mapping[str, Any]],
    problem_docs: Sequence[Mapping[str, Any]],
) -> list[str]:
    warnings = [warning for document in documents for warning in document["warnings"]]
    if stale_tax_docs and not any("impot" in warning.lower() or "fiscal" in warning.lower() for warning in warnings):
        warnings.append("Avis d impot possiblement obsolete.")
    if problem_docs:
        warnings.append("Certains documents contiennent des erreurs d extraction.")
    return warnings


def sequence_value(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
        return sequence_value(parsed)
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)

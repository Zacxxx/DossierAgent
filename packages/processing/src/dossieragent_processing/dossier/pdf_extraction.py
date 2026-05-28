from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PdfExtractionResult:
    text: str
    page_count: int
    detected_type: str | None
    issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = list(self.issues)
        payload["warnings"] = list(self.warnings)
        return payload


def extract_pdf_text(
    pdf_path: str | Path,
    *,
    declared_type: str | None = None,
) -> PdfExtractionResult:
    path = Path(pdf_path)
    try:
        import fitz
    except Exception as exc:  # pragma: no cover - dependency failure path.
        return PdfExtractionResult(
            text="",
            page_count=0,
            detected_type=None,
            issues=(f"pymupdf_unavailable: {exc}",),
        )

    try:
        document = fitz.open(path)
    except Exception as exc:
        return PdfExtractionResult(
            text="",
            page_count=0,
            detected_type=None,
            issues=(f"pdf_open_failed: {exc}",),
        )

    issues: list[str] = []
    warnings: list[str] = []
    page_texts: list[str] = []
    try:
        page_count = document.page_count
        for index, page in enumerate(document):
            try:
                blocks = page.get_text("blocks", sort=True)
            except Exception as exc:
                warnings.append(f"page_{index + 1}_text_failed: {exc}")
                continue

            lines = [
                cleaned
                for block in blocks
                if len(block) >= 5
                for cleaned in (clean_text(str(block[4])),)
                if cleaned
            ]
            page_text = "\n".join(lines)
            if page_text:
                page_texts.append(page_text)
            else:
                warnings.append(f"page_{index + 1}_empty_text")
    finally:
        document.close()

    text = clean_text("\n\n".join(page_texts))
    if page_count == 0:
        issues.append("empty_pdf")
    if len(text) < 40:
        issues.append("insufficient_extractable_text")

    detected_type = detect_document_type(text, declared_type=declared_type)
    if detected_type is None:
        warnings.append("document_type_not_detected")

    return PdfExtractionResult(
        text=text,
        page_count=page_count,
        detected_type=detected_type,
        issues=tuple(dict.fromkeys(issues)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def detect_document_type(text: str, *, declared_type: str | None = None) -> str | None:
    normalized = normalize_text(text)
    rules = (
        ("payslip", ("bulletin de paie", "fiche de paie", "salaire net", "net a payer")),
        ("employment_contract", ("contrat de travail", "cdi", "cdd", "employeur")),
        ("tax_notice", ("avis d impot", "avis d'imposition", "revenu fiscal", "impot sur le revenu")),
        ("identity", ("carte nationale", "passeport", "date de naissance", "piece d identite")),
        ("proof_of_address", ("justificatif de domicile", "facture", "adresse de consommation")),
    )
    for document_type, markers in rules:
        if any(marker in normalized for marker in markers):
            return document_type

    if declared_type and declared_type.strip():
        return declared_type.strip()
    return None


def clean_text(value: str) -> str:
    compact_lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in compact_lines if line)


def normalize_text(value: str) -> str:
    lowered = value.lower()
    replacements = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ù": "u",
        "û": "u",
        "ç": "c",
    }
    for source, target in replacements.items():
        lowered = lowered.replace(source, target)
    return re.sub(r"\s+", " ", lowered)

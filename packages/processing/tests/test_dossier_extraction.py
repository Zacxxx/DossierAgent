from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dossieragent_processing import analyze_dossier, extract_pdf_text


class DossierExtractionTests(unittest.TestCase):
    def test_extract_pdf_text_reads_blocks_and_detects_document_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "payslip.pdf"
            pdf_path.write_bytes(
                build_pdf_bytes(
                    "Bulletin de paie mai 2026\nEmployeur DossierAgent SAS\nSalaire net a payer 2450 EUR"
                )
            )

            result = extract_pdf_text(pdf_path, declared_type="payslip")

        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.detected_type, "payslip")
        self.assertIn("Bulletin de paie", result.text)
        self.assertEqual(result.issues, ())

    def test_extract_pdf_text_marks_invalid_pdf_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_path = Path(tmp_dir) / "bad.pdf"
            bad_path.write_text("not a pdf", encoding="utf-8")

            result = extract_pdf_text(bad_path)

        self.assertEqual(result.page_count, 0)
        self.assertEqual(result.text, "")
        self.assertTrue(result.issues)
        self.assertTrue(result.issues[0].startswith("pdf_open_failed"))

    def test_analyze_dossier_scores_missing_contract_and_stale_tax_notice(self) -> None:
        result = analyze_dossier(
            [
                document("doc_identity", "identity", "valid"),
                document("doc_payslip_march", "payslip", "valid"),
                document("doc_payslip_april", "payslip", "valid"),
                document("doc_payslip_may", "payslip", "valid"),
                document(
                    "doc_tax_notice",
                    "tax_notice",
                    "needs_review",
                    warnings=["Avis d impot possiblement obsolete."],
                ),
                document(
                    "doc_employment_contract_missing",
                    "employment_contract",
                    "needs_review",
                    detected_type=None,
                    issues=["Piece manquante dans le dossier de demo"],
                ),
            ]
        )

        self.assertEqual(result.readiness_score, 78)
        self.assertTrue(result.can_contact)
        self.assertFalse(result.can_send_full_dossier)
        self.assertEqual(
            {missing.type for missing in result.missing_documents},
            {"employment_contract", "latest_tax_notice"},
        )
        self.assertIn("doc_identity", result.valid_documents)
        self.assertIn("Avis d impot possiblement obsolete.", result.warnings)

    def test_analyze_dossier_blocks_contact_without_identity_or_income(self) -> None:
        result = analyze_dossier([document("doc_tax_notice", "tax_notice", "valid")])

        self.assertEqual(result.readiness_score, 10)
        self.assertFalse(result.can_contact)
        self.assertFalse(result.can_send_full_dossier)
        self.assertEqual(
            {missing.type for missing in result.missing_documents},
            {"identity", "recent_income", "employment_contract"},
        )


def build_pdf_bytes(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    try:
        return document.tobytes()
    finally:
        document.close()


def document(
    document_id: str,
    declared_type: str,
    status: str,
    *,
    detected_type: str | None = "",
    issues: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": document_id,
        "filename": f"{document_id}.pdf",
        "declared_type": declared_type,
        "detected_type": declared_type if detected_type == "" else detected_type,
        "status": status,
        "issues_json": issues or [],
        "warnings_json": warnings or [],
    }


if __name__ == "__main__":
    unittest.main()

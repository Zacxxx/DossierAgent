from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dossieragent_processing import extract_pdf_text


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


def build_pdf_bytes(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    try:
        return document.tobytes()
    finally:
        document.close()


if __name__ == "__main__":
    unittest.main()

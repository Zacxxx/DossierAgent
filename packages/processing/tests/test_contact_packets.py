from __future__ import annotations

import unittest

from dossieragent_processing import build_contact_packet


class ContactPacketTests(unittest.TestCase):
    def test_build_contact_packet_uses_listing_risks_and_dossier_summary(self) -> None:
        draft = build_contact_packet(
            {
                "title": "T2 Saint-Cyprien proche metro",
                "city": "Toulouse",
                "district": "Saint-Cyprien",
                "risk_flags_json": '["charges_non_detaillees","disponibilite_non_precisee"]',
            },
            dossier_summary={
                "can_contact": True,
                "can_send_full_dossier": False,
                "missing_documents": ["employment_contract"],
                "readiness_score": 78,
            },
        )

        self.assertIn("T2 Saint-Cyprien", draft.message_draft)
        self.assertIn("validation manuelle", draft.message_draft)
        self.assertIn("Les charges sont elles incluses et detaillees ?", draft.questions_to_ask)
        self.assertIn("Quelle est la date de disponibilite du logement ?", draft.questions_to_ask)
        self.assertEqual(draft.dossier_summary["missing_documents"], ["employment_contract"])

    def test_build_contact_packet_does_not_claim_attachment_or_completion(self) -> None:
        draft = build_contact_packet({"title": "T2 Carmes"}, dossier_summary={"can_contact": False})

        self.assertNotIn("joint", draft.message_draft.lower())
        self.assertNotIn("complet", draft.message_draft.lower())
        self.assertEqual(len(draft.questions_to_ask), 2)


if __name__ == "__main__":
    unittest.main()

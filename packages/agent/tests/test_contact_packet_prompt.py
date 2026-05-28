from __future__ import annotations

import unittest

from dossieragent_agent import CONTACT_PACKET_PROMPT, CONTACT_PACKET_RESPONSE_SCHEMA


class ContactPacketPromptTests(unittest.TestCase):
    def test_prompt_requires_json_and_supervision_rules(self) -> None:
        self.assertIn("Retourne uniquement du JSON", CONTACT_PACKET_PROMPT)
        self.assertIn("N'affirme jamais qu'un document est joint", CONTACT_PACKET_PROMPT)
        self.assertIn("N'affirme jamais que le dossier est complet sans preuve", CONTACT_PACKET_PROMPT)
        self.assertIn("langue demandee", CONTACT_PACKET_PROMPT)

    def test_response_schema_requires_packet_fields(self) -> None:
        self.assertFalse(CONTACT_PACKET_RESPONSE_SCHEMA["additionalProperties"])
        self.assertEqual(
            set(CONTACT_PACKET_RESPONSE_SCHEMA["required"]),
            {"message_draft", "questions_to_ask", "dossier_summary"},
        )


if __name__ == "__main__":
    unittest.main()

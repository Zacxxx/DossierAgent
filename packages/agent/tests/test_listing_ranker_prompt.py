from __future__ import annotations

import unittest

from dossieragent_agent import LISTING_RANKER_PROMPT, LISTING_RANKER_RESPONSE_SCHEMA


class ListingRankerPromptTests(unittest.TestCase):
    def test_prompt_forbids_invention_and_requires_json(self) -> None:
        self.assertIn("Retourne uniquement du JSON", LISTING_RANKER_PROMPT)
        self.assertIn("N'invente jamais", LISTING_RANKER_PROMPT)
        self.assertIn("Tu ne modifies jamais le score deterministe", LISTING_RANKER_PROMPT)
        self.assertIn("Le score final doit etre compris entre 0 et 100", LISTING_RANKER_PROMPT)

    def test_response_schema_is_constrained(self) -> None:
        self.assertFalse(LISTING_RANKER_RESPONSE_SCHEMA["additionalProperties"])
        self.assertEqual(
            set(LISTING_RANKER_RESPONSE_SCHEMA["required"]),
            {"fit_score", "fit_level", "reasons", "risk_flags", "recommendation"},
        )
        self.assertEqual(
            LISTING_RANKER_RESPONSE_SCHEMA["properties"]["fit_level"]["enum"],
            ["strong", "medium", "low"],
        )


if __name__ == "__main__":
    unittest.main()

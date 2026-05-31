from __future__ import annotations

import unittest

from dossieragent_agent import parse_command


class CommandParserTests(unittest.TestCase):
    def test_parse_run_watch_command(self) -> None:
        parsed = parse_command("Lance un scan de la veille watch_toulouse_t2")

        self.assertEqual(parsed.status, "accepted")
        self.assertEqual(parsed.intent, "run_market_watch")
        self.assertEqual(parsed.action, "run_watch_now")
        self.assertEqual(parsed.parameters["watch_id"], "watch_toulouse_t2")

    def test_parse_analyze_dossier_command(self) -> None:
        parsed = parse_command("Analyse mon dossier")

        self.assertEqual(parsed.status, "accepted")
        self.assertEqual(parsed.intent, "analyze_dossier")
        self.assertEqual(parsed.action, "create_dossier_snapshot")

    def test_parse_create_watch_command(self) -> None:
        parsed = parse_command("Cree une veille pour Lyon budget 900 T2")

        self.assertEqual(parsed.status, "accepted")
        self.assertEqual(parsed.intent, "create_market_watch")
        self.assertEqual(parsed.parameters["city"], "Lyon")
        self.assertEqual(parsed.parameters["budget_max"], 900.0)
        self.assertEqual(parsed.parameters["rooms_min"], 2.0)

    def test_reject_autonomous_external_contact(self) -> None:
        parsed = parse_command("Envoie un email au proprietaire pour cette annonce")

        self.assertEqual(parsed.status, "rejected")
        self.assertEqual(parsed.intent, "blocked_external_contact")
        self.assertIn("no_autonomous_email", parsed.guardrails)


if __name__ == "__main__":
    unittest.main()

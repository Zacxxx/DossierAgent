from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from dossieragent_core.api import create_app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "dossieragent-core"})

    def test_openapi_is_available(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["info"]["title"], "DossierAgent API")
        self.assertIn("/health", payload["paths"])

    def test_not_found_uses_spec_error_envelope(self) -> None:
        response = self.client.get("/missing")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "not_found")
        self.assertEqual(payload["error"]["message"], "Route introuvable.")
        self.assertEqual(payload["error"]["details"], {"path": "/missing"})
        self.assertFalse(payload["error"]["retryable"])
        self.assertRegex(payload["error"]["trace_id"], re.compile(r"^trc_[a-f0-9]{12}$"))


if __name__ == "__main__":
    unittest.main()


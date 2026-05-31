from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from dossieragent_browser.adapters import UnknownSourceError, default_adapter_registry
from dossieragent_browser.artifacts import ArtifactWriter
from dossieragent_browser.extractors import ExtractionRejected, extract_listing_details, extract_listing_urls
from dossieragent_browser.guards import ComplianceGuard
from dossieragent_browser.jobs import BrowserJob, BrowserJobError
from dossieragent_browser.worker import main, run_browser_job


LISTING_HTML = """
<!doctype html>
<html>
  <head>
    <title>Fallback title</title>
    <link rel="canonical" href="https://demo.example/listings/t2-saint-cyprien?utm=1" />
    <meta name="description" content="T2 proche metro, disponible pour contact agence." />
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Apartment",
        "name": "T2 Saint-Cyprien proche metro",
        "description": "Appartement lumineux avec balcon.",
        "url": "https://demo.example/listings/t2-saint-cyprien",
        "image": [
          "https://cdn.demo.example/listings/t2-saint-cyprien.jpg",
          {"url": "/images/t2-saint-cyprien-bedroom.jpg"}
        ],
        "sku": "demo-123",
        "numberOfRooms": 2,
        "floorSize": {"@type": "QuantitativeValue", "value": 39, "unitCode": "MTK"},
        "offers": {"@type": "Offer", "price": "790", "priceCurrency": "EUR"},
        "address": {
          "@type": "PostalAddress",
          "addressLocality": "Toulouse",
          "addressRegion": "Saint-Cyprien",
          "postalCode": "31000"
        },
        "seller": {"@type": "RealEstateAgent", "name": "Agence Demo Toulouse"}
      }
    </script>
  </head>
  <body>
    <main>
      <h1>T2 Saint-Cyprien proche metro</h1>
      <img src="/images/t2-saint-cyprien-living.jpg" alt="Salon" />
      <p>39 m2 - 2 pieces - contact agence.</p>
    </main>
  </body>
</html>
"""

LIST_PAGE_HTML = """
<!doctype html>
<html>
  <body>
    <section data-results>
      <a href="/listings/seed-001" data-listing-id="seed-001" data-price="790"
         data-surface="39" data-city="Toulouse" data-district="Saint-Cyprien"
         data-image-url="/images/seed-001.jpg">
        T2 Saint-Cyprien proche metro - 790 EUR - 39 m2
      </a>
      <a href="https://demo.example/listings/seed-002" data-listing-id="seed-002">
        <img src="/images/seed-002.jpg" alt="Carmes" />
        T2 Carmes calme - 820 EUR - 38 m2
      </a>
      <a href="mailto:agency@example.test">Contact</a>
      <a href="/listings/seed-001">Duplicate</a>
    </section>
  </body>
</html>
"""


class BrowserDirectUrlTests(unittest.TestCase):
    def test_browser_job_validates_direct_url_payload(self) -> None:
        job = BrowserJob.from_mapping(
            {
                "job_id": "job_001",
                "source": "manual_url",
                "mode": "direct_url",
                "criteria": {"url": "https://demo.example/listings/1"},
                "timeout": 12,
            }
        )

        self.assertEqual(job.job_id, "job_001")
        self.assertEqual(job.source, "manual_url")
        self.assertEqual(job.mode, "direct_url")
        self.assertEqual(job.timeout, 12.0)
        self.assertEqual(job.direct_url(), "https://demo.example/listings/1")

        with self.assertRaises(BrowserJobError):
            BrowserJob.from_mapping({"mode": "agent_browser", "criteria": {}})

    def test_direct_url_extractor_returns_normalized_listing_candidate(self) -> None:
        candidate = extract_listing_details(
            "https://demo.example/listings/t2-saint-cyprien?tracking=1",
            source="demo_seed",
            html=LISTING_HTML,
        )

        self.assertEqual(candidate["source"], "demo_seed")
        self.assertEqual(candidate["source_url"], "https://demo.example/listings/t2-saint-cyprien?tracking=1")
        self.assertEqual(candidate["canonical_url"], "https://demo.example/listings/t2-saint-cyprien")
        self.assertEqual(candidate["source_listing_id"], "demo-123")
        self.assertEqual(candidate["title"], "T2 Saint-Cyprien proche metro")
        self.assertEqual(candidate["city"], "Toulouse")
        self.assertEqual(candidate["district"], "Saint-Cyprien")
        self.assertEqual(candidate["postal_code"], "31000")
        self.assertEqual(candidate["price"], 790.0)
        self.assertEqual(candidate["surface"], 39.0)
        self.assertEqual(candidate["rooms"], 2.0)
        self.assertEqual(candidate["agency_name"], "Agence Demo Toulouse")
        self.assertEqual(candidate["contact_hint"], "contact present on page")
        self.assertEqual(
            candidate["raw_payload"]["image_urls"],
            [
                "https://cdn.demo.example/listings/t2-saint-cyprien.jpg",
                "https://demo.example/images/t2-saint-cyprien-bedroom.jpg",
                "https://demo.example/images/t2-saint-cyprien-living.jpg",
            ],
        )

    def test_direct_url_extractor_rejects_login_or_captcha_pages(self) -> None:
        with self.assertRaises(ExtractionRejected):
            extract_listing_details(
                "https://demo.example/listings/blocked",
                source="demo_seed",
                html="<html><body>Captcha required before viewing this listing.</body></html>",
            )

    def test_compliance_guard_rejects_non_allowlisted_sources(self) -> None:
        job = BrowserJob.from_mapping(
            {
                "job_id": "job_blocked",
                "source": "unknown_source",
                "mode": "direct_url",
                "criteria": {"url": "https://demo.example/listings/blocked"},
            }
        )

        with self.assertRaisesRegex(Exception, "not allowlisted"):
            ComplianceGuard().check_job(job)

    def test_degraded_job_writes_diagnostic_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            job = BrowserJob.from_mapping(
                {
                    "job_id": "job_failure",
                    "source": "demo_seed",
                    "mode": "direct_url",
                    "criteria": {"url": "https://demo.example/listings/bad"},
                    "timeout": 5,
                }
            )
            result = run_browser_job(
                job,
                html="<html><body>Missing a usable title</body></html>",
                artifact_writer=ArtifactWriter(tmp_dir),
            )

            self.assertEqual(result.status, "degraded")
            self.assertEqual(result.error["type"], "ExtractionError")
            self.assertTrue(Path(result.artifacts[0]).exists())

            html_path = Path(tmp_dir) / "listing.html"
            html_path.write_text("<html><body>Missing a usable title</body></html>", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--url",
                        "https://demo.example/listings/bad",
                        "--source",
                        "demo_seed",
                        "--html-file",
                        str(html_path),
                        "--artifact-dir",
                        tmp_dir,
                    ]
                )

            self.assertEqual(exit_code, 0)
            cli_payload = json.loads(stdout.getvalue())
            self.assertEqual(cli_payload["status"], "degraded")
            failure_path = Path(cli_payload["artifacts"][0])
            self.assertTrue(failure_path.exists())
            payload = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["error"]["type"], "ExtractionError")

    def test_artifact_writer_stores_json_html_screenshot_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            job = BrowserJob.from_mapping(
                {
                    "job_id": "job_artifacts",
                    "source": "demo_seed",
                    "mode": "direct_url",
                    "criteria": {"url": "https://demo.example/listings/ok"},
                }
            )
            paths = ArtifactWriter(tmp_dir).write_success(
                job,
                {"title": "T2"},
                html="<html></html>",
                screenshot=b"png-bytes",
                trace=b"zip-bytes",
            )

            self.assertEqual(
                {path.name for path in paths},
                {"listing.json", "page.html", "screenshot.png", "trace.zip"},
            )

    def test_worker_idle_mode_is_root_launchable(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "idle")

    def test_adapter_registry_rejects_unknown_sources(self) -> None:
        with self.assertRaises(UnknownSourceError):
            default_adapter_registry().get("unknown_source")

    def test_list_page_extractor_returns_listing_urls_and_card_metadata(self) -> None:
        result = extract_listing_urls(
            "demo_seed",
            {"url": "https://demo.example/search/toulouse"},
            html=LIST_PAGE_HTML,
        )

        self.assertEqual(result["source"], "demo_seed")
        self.assertEqual(len(result["items"]), 2)
        first = result["items"][0]
        self.assertEqual(first["listing_url"], "https://demo.example/listings/seed-001")
        self.assertEqual(first["source_listing_id"], "seed-001")
        self.assertEqual(first["title"], "T2 Saint-Cyprien proche metro - 790 EUR - 39 m2")
        self.assertEqual(first["price"], 790.0)
        self.assertEqual(first["surface"], 39.0)
        self.assertEqual(first["city"], "Toulouse")
        self.assertEqual(first["district"], "Saint-Cyprien")
        self.assertEqual(
            first["raw_payload"]["image_urls"],
            ["https://demo.example/images/seed-001.jpg"],
        )
        self.assertEqual(
            result["items"][1]["raw_payload"]["image_urls"],
            ["https://demo.example/images/seed-002.jpg"],
        )

    def test_worker_runs_list_page_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            job = BrowserJob.from_mapping(
                {
                    "job_id": "job_list",
                    "source": "demo_seed",
                    "mode": "list_page",
                    "criteria": {"url": "https://demo.example/search/toulouse"},
                }
            )

            result = run_browser_job(
                job,
                artifact_writer=ArtifactWriter(tmp_dir),
                html=LIST_PAGE_HTML,
            )

            self.assertEqual(result.status, "succeeded")
            self.assertEqual(len(result.candidate["items"]), 2)
            self.assertTrue(Path(result.artifacts[0]).exists())


if __name__ == "__main__":
    unittest.main()

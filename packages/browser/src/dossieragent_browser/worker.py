from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dossieragent_browser.artifacts import ArtifactWriter
from dossieragent_browser.extractors import DirectUrlExtractor, StaticHtmlLoader
from dossieragent_browser.guards import ComplianceGuard
from dossieragent_browser.jobs import BrowserJob, BrowserJobError, BrowserJobResult


def run_browser_job(
    job: BrowserJob,
    *,
    artifact_writer: ArtifactWriter | None = None,
    compliance_guard: ComplianceGuard | None = None,
    html: str | None = None,
) -> BrowserJobResult:
    writer = artifact_writer or ArtifactWriter()
    guard = compliance_guard or ComplianceGuard.from_env()
    loaded_html: str | None = None
    try:
        if job.mode != "direct_url":
            raise BrowserJobError(f"Unsupported implemented browser job mode: {job.mode}")
        guard.check_job(job)
        guard.before_request()

        loader = StaticHtmlLoader(html) if html is not None else None
        extractor = DirectUrlExtractor(loader=loader)
        candidate, loaded_page = extractor.extract(
            job.direct_url(),
            source=job.source,
            criteria=job.criteria,
            timeout=job.timeout,
        )
        loaded_html = loaded_page.html
        artifacts = writer.write_success(
            job,
            candidate.as_dict(),
            html=loaded_page.html,
            screenshot=loaded_page.screenshot,
            trace=loaded_page.trace,
        )
        return BrowserJobResult(
            job_id=job.job_id,
            status="succeeded",
            mode=job.mode,
            source=job.source,
            candidate=candidate.as_dict(),
            artifacts=tuple(str(path) for path in artifacts),
        )
    except Exception as exc:
        artifacts = writer.write_failure(job, exc, html=loaded_html or html)
        return BrowserJobResult(
            job_id=job.job_id,
            status="degraded",
            mode=job.mode,
            source=job.source,
            error={"type": type(exc).__name__, "message": str(exc)},
            artifacts=tuple(str(path) for path in artifacts),
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.job_json is None and args.url is None:
        idle_result = BrowserJobResult(
            job_id="idle",
            status="idle",
            mode="direct_url",
            source="browser-worker",
        )
        print(json.dumps(idle_result.as_dict(), sort_keys=True))
        return 0

    try:
        payload = load_job_payload(args)
        job = BrowserJob.from_mapping(payload)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2

    html = Path(args.html_file).read_text(encoding="utf-8") if args.html_file else None
    writer = ArtifactWriter(args.artifact_dir)
    result = run_browser_job(job, artifact_writer=writer, html=html)
    print(json.dumps(result.as_dict(), sort_keys=True))
    return 0 if result.status in {"succeeded", "degraded"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DossierAgent browser extraction worker")
    parser.add_argument("--job-json", help="JSON object or @path containing a BrowserJob payload")
    parser.add_argument("--url", help="Direct listing URL for ad hoc extraction")
    parser.add_argument("--source", default="manual_url", help="Source identifier for --url jobs")
    parser.add_argument("--criteria-json", default="{}", help="Criteria JSON used by extractors")
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout in seconds")
    parser.add_argument("--html-file", help="Read already-rendered HTML from a local file")
    parser.add_argument("--artifact-dir", help="Directory where artifacts are written")
    return parser


def load_job_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.job_json is not None:
        raw_payload = args.job_json
        if raw_payload.startswith("@"):
            raw_payload = Path(raw_payload[1:]).read_text(encoding="utf-8")
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            raise BrowserJobError("Browser job JSON must be an object.")
        return payload

    criteria = json.loads(args.criteria_json)
    if not isinstance(criteria, dict):
        raise BrowserJobError("Criteria JSON must be an object.")
    criteria = {**criteria, "url": args.url}
    return {
        "source": args.source,
        "mode": "direct_url",
        "criteria": criteria,
        "timeout": args.timeout,
    }


if __name__ == "__main__":
    raise SystemExit(main())

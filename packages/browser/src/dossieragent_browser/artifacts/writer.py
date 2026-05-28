from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dossieragent_browser.jobs import BrowserJob


class ArtifactWriter:
    def __init__(self, base_path: str | os.PathLike[str] | None = None) -> None:
        default_base = Path(os.environ.get("DOSSIERAGENT_STORAGE_PATH", "storage")) / "browser"
        self.base_path = Path(base_path) if base_path is not None else default_base

    def job_path(self, job: BrowserJob) -> Path:
        safe_job_id = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in job.job_id
        )
        path = self.base_path / safe_job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, job: BrowserJob, filename: str, payload: Mapping[str, Any]) -> Path:
        path = self.job_path(job) / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def write_text(self, job: BrowserJob, filename: str, content: str) -> Path:
        path = self.job_path(job) / filename
        path.write_text(content, encoding="utf-8")
        return path

    def write_bytes(self, job: BrowserJob, filename: str, content: bytes) -> Path:
        path = self.job_path(job) / filename
        path.write_bytes(content)
        return path

    def write_success(
        self,
        job: BrowserJob,
        candidate: Mapping[str, Any],
        html: str | None = None,
        screenshot: bytes | None = None,
        trace: bytes | None = None,
    ) -> tuple[Path, ...]:
        paths = [self.write_json(job, "listing.json", candidate)]
        if html:
            paths.append(self.write_text(job, "page.html", html))
        if screenshot:
            paths.append(self.write_bytes(job, "screenshot.png", screenshot))
        if trace:
            paths.append(self.write_bytes(job, "trace.zip", trace))
        return tuple(paths)

    def write_failure(
        self,
        job: BrowserJob,
        error: BaseException,
        *,
        html: str | None = None,
        screenshot: bytes | None = None,
        trace: bytes | None = None,
    ) -> tuple[Path, ...]:
        payload = {
            "job": job.as_dict(),
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }
        paths = [self.write_json(job, "failure.json", payload)]
        if html:
            paths.append(self.write_text(job, "page.html", html))
        if screenshot:
            paths.append(self.write_bytes(job, "screenshot.png", screenshot))
        if trace:
            paths.append(self.write_bytes(job, "trace.zip", trace))
        return tuple(paths)

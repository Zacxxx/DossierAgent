PACKAGE_MANIFEST = {
    "name": "browser",
    "concern": "Playwright-controlled listing extraction.",
    "owns": (
        "browser jobs",
        "source adapters",
        "list page extraction",
        "detail page extraction",
        "browser artifacts",
        "compliance guards",
    ),
    "exposes": (
        "extract_listing_urls",
        "extract_listing_details",
        "BrowserJob",
        "run_browser_job",
    ),
    "events": (
        "browser.job.started",
        "browser.job.finished",
        "browser.job.failed",
    ),
}


def get_manifest() -> dict[str, object]:
    return dict(PACKAGE_MANIFEST)


from dossieragent_browser.extractors import extract_listing_details
from dossieragent_browser.jobs import BrowserJob, BrowserJobResult


def run_browser_job(*args: object, **kwargs: object) -> object:
    from dossieragent_browser.worker import run_browser_job as _run_browser_job

    return _run_browser_job(*args, **kwargs)

__all__ = [
    "BrowserJob",
    "BrowserJobResult",
    "PACKAGE_MANIFEST",
    "extract_listing_details",
    "get_manifest",
    "run_browser_job",
]

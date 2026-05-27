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
    ),
    "events": (
        "browser.job.started",
        "browser.job.finished",
        "browser.job.failed",
    ),
}


def get_manifest() -> dict[str, object]:
    return dict(PACKAGE_MANIFEST)


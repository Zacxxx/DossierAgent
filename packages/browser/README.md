# `browser`

Playwright extraction package.

## Owns

- browser jobs
- source adapters
- list-page extraction
- detail-page extraction
- trace, screenshot, and HTML artifacts
- compliance guards

## Does Not Own

- deduplication
- ranking
- persistence
- contact packet generation

## Public Surface

- `extract_listing_urls`
- `extract_listing_details`
- source adapter registry
- `BrowserJob`
- `run_browser_job`

## Local Commands

- `python3 -m dossieragent_browser.worker`
- `python3 -m dossieragent_browser.worker --url https://example.test/listing --html-file /tmp/listing.html`

The worker never attempts login or captcha bypass. Direct URL extraction can use Playwright for live pages, while tests and seeded runs can pass already-rendered HTML through `--html-file`.

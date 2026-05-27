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


# `processing`

Deterministic processing package.

## Owns

- listing normalization
- deduplication
- deterministic ranking
- dossier PDF text extraction and readiness scoring
- contact packet draft preparation

## Does Not Own

- long-running orchestration
- persistence engines
- Elastic index operations
- browser navigation

## Public Surface

- `normalize_listing`
- `deduplicate_listing`
- `rank_listing`
- `analyze_dossier`
- `build_contact_packet`

## Listing Dedupe

The listing flow is deterministic and hierarchical:

1. normalize canonical URL and hash it as `canonical_url_hash`
2. build `composite_fingerprint` from location, price, surface, agency, and title
3. mark exact duplicates by canonical URL hash or `source + source_listing_id`
4. score quasi-exact candidates with the spec weights and thresholds

Thresholds live in `DedupeThresholds` and default to:

- duplicate: `>= 0.92`
- repost: `>= 0.82`
- changed listing: `>= 0.75` with price or surface variation

## Listing Ranking

`rank_listing` applies the spec weights deterministically:

- budget: 25
- surface: 20
- location: 20
- text signals: 15
- freshness: 10
- dossier alignment: 10
- risk penalties: up to -30

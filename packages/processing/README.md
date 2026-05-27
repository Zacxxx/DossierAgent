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


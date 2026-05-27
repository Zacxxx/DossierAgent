# `search_engine`

Elasticsearch package.

## Owns

- `listings_v1` mapping
- `documents_v1` mapping
- indexing payloads
- lexical, vector, and hybrid query builders
- search health checks

## Does Not Own

- SQLite source of truth
- MCP server hosting
- browser extraction
- deterministic business decisions

## Public Surface

- index bootstrap
- listing indexing
- document indexing
- hybrid listing search

## Mapping Artifacts

- `mappings/listings_v1.json`
- `mappings/documents_v1.json`

Both mappings use app-generated `dense_vector` fields with 768 dimensions and
keep scalar fields for UI filters, sorting, and auditability.

## Listing Search Query

`build_listing_search_query` builds an Elasticsearch request body from scalar
filters (`status`, `city`, `district`, price, surface, score) plus lexical `q`
search. `core` can call it when Elastic is configured, while SQLite remains the
local fallback and operational source of truth.

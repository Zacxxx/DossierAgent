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


# Package Architecture

The specification describes a supervised rental-search agent, not one large backend. The repository is therefore split by bounded concern. Packages are isolated by default and are composed by the tiny `core` package.

## Dependency Rule

Feature packages must not import other feature packages.

Allowed:

```text
frontend -> HTTP API only
core -> explicit package manifests/adapters
package -> external libraries owned by that package
```

Not allowed:

```text
agent -> database
browser -> processing
processing -> search_engine
schedule -> agent
mcp -> search_engine
```

When one concern needs another at runtime, the dependency is passed in by `core` as a callable, port, client, or configuration object. This keeps package implementation testable and independently replaceable.

## Core Contract

`packages/core` stays deliberately small. It owns:

- package registry
- package manifest loading
- runtime composition
- lifecycle orchestration
- cross-package capability lookup

It does not own:

- API business handlers
- database schema
- search mappings
- browser extraction rules
- prompts
- PDF processing
- scheduling policy
- frontend state

## Package Ownership

| Package | Owns | Explicitly does not own |
|---|---|---|
| `frontend` | Dashboard, listings, dossier, contact packets, checks, notifications UI | Domain algorithms, scraping, persistence |
| `agent` | `POST /agent/commands`, agent run intent planning, prompt contracts, supervised tool definitions | SQLite repositories, Elastic queries, browser extraction implementation |
| `database` | SQLite WAL setup, migrations, table definitions, repository primitives | Ranking, PDF extraction, API orchestration |
| `search_engine` | `listings_v1`, `documents_v1`, hybrid search, kNN/RRF query builders | SQLite truth, MCP server hosting, user checks |
| `browser` | Playwright jobs, source adapters, list/detail extraction, traces and screenshots | Deduplication, ranking, contact packets |
| `schedule` | Due-watch calculation, cron entrypoints, frequency policy | Running browser jobs directly, agent reasoning |
| `processing` | Listing normalization, dedupe, deterministic scoring, dossier extraction/classification, contact packet drafts | Long-running orchestration, storage engines |
| `mcp` | Elastic Agent Builder MCP config, MCP tool exposure, MCP security defaults | App search implementation, domain ranking |
| `core` | Registry and composition only | Product logic |

## Main Runtime Flows

### Command to Watch

```text
frontend
  -> core API composition
  -> agent parses command
  -> database stores criteria/watch/run
  -> frontend receives structured preview and checks
```

### Watch Run

```text
schedule or frontend run-now
  -> core orchestration
  -> database creates agent_run/events
  -> browser extracts candidates
  -> processing normalizes, deduplicates, ranks
  -> search_engine indexes/searches
  -> database stores listings/events/notifications
  -> frontend polls dashboard and run timeline
```

### Dossier Analysis

```text
frontend upload
  -> database stores document metadata
  -> processing extracts PDF text and readiness snapshot
  -> search_engine indexes document text
  -> database stores dossier snapshot and checks
```

### Contact Packet

```text
frontend selects listing
  -> processing builds packet draft
  -> agent applies supervised language contract
  -> database stores packet and user_check
  -> frontend review panel shows pending validation
```

## Adding New Work

1. Put implementation in the package that owns the concern.
2. Expose only a narrow public adapter or manifest from that package.
3. Wire that adapter from `packages/core`.
4. Keep tests inside the owning package.
5. Do not import one feature package from another to save a few lines.


# DossierAgent

Supervised housing-search agent for building, tracking, and using a rental dossier without pretending the agent should act alone.

DossierAgent is designed around a credible MVP loop: define a watch, scan sources, avoid duplicates, qualify listings, analyze dossier documents, prepare a contact packet, and ask the user for explicit validation before any sensitive action.

## Why This Exists

Rental search is repetitive and fragmented, but the risky part is not just finding listings. The hard part is keeping memory, understanding whether a dossier is actually ready, explaining why a listing is worth attention, and keeping the human in control before contact.

DossierAgent is therefore a command center, not an autopilot.

## Current Shape

The repository is a package-based monorepo:

```text
packages/<package_name>
```

Each package owns one concern and can be maintained independently. Feature packages do not import each other. The `core` package is intentionally small and exists to stitch capabilities together at the application boundary.

| Package | Owns |
|---|---|
| `frontend` | Desktop-first command center UI |
| `agent` | Supervised commands, runs, tools, and prompt contracts |
| `database` | SQLite schema, migrations, repositories, and seed data |
| `search_engine` | Elasticsearch mappings, indexing, and hybrid search |
| `browser` | Playwright extraction worker and source adapters |
| `schedule` | Cron-facing watch scheduling and due-run policy |
| `processing` | Listing normalization, dedupe, ranking, dossier analysis, and contact packets |
| `mcp` | Elastic Agent Builder MCP integration and MCP configuration |
| `core` | Minimal composition, registry, and runtime launcher glue |

## Run From Root

Use either Bun or npm from the repository root:

```bash
bun run dev
npm run dev
```

Useful commands:

| Command | Purpose |
|---|---|
| `bun run dev` / `npm run dev` | Launch implemented runtime services from the root supervisor |
| `bun run start` / `npm run start` | Production-style root startup entrypoint |
| `bun run status` / `npm run status` | Show package and service readiness |
| `bun run packages` / `npm run packages` | List package concerns |
| `bun run seed` / `npm run seed` | Create/update the deterministic local demo database |
| `bun run check` / `npm run check` | Compile Python packages and enforce package isolation |

Today the root launcher starts:

- Core API shell: `http://127.0.0.1:8000`
- Frontend shell: `http://127.0.0.1:5173`

Seed local demo data before exercising API or UI flows:

```bash
bun run seed
```

The seed command writes to SQLite and generated demo storage artifacts. API and frontend work should read this state instead of embedding placeholder data.

## Architecture

The dependency rule is strict:

```text
feature package -> external dependencies only
frontend -> HTTP API only
core -> package manifests, adapters, and composition
```

Feature packages should communicate through explicit ports, callables, API contracts, events, or DTOs passed by `core`. They should not import each other to save time.

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing package boundaries.

## Product Surface

The MVP is intentionally supervised:

- Dashboard with active watch, latest run, dossier readiness, pending checks, and notifications
- Watches with criteria, frequency, and manual `run now`
- Listings with duplicate/repost handling, score explanations, risk flags, and user decisions
- Dossier upload and readiness analysis
- Contact packet generation for manual review and copy
- History with run events and traceability

## Roadmap

Work is tracked as sprint-based GitHub issues. The source-of-truth product and technical scope is [spec-AgentDossier.md](spec-AgentDossier.md). The sprint breakdown is summarized in [docs/ROADMAP.md](docs/ROADMAP.md).

## Agent Workflow

Agents and contributors must follow [AGENTS.md](AGENTS.md):

- pick work from GitHub issues
- cite the relevant spec section before implementation
- keep changes inside the owning package
- comment on issues with progress and verification
- close issues only after acceptance criteria are met

## Development Principles

- Keep the user in control. No automatic external contact in the MVP.
- Store operational truth in SQLite.
- Use Elastic for search and market memory, not as the source of truth.
- Use Playwright for controlled extraction with compliance guards.
- Use `core` for orchestration only.
- Prefer visible end-to-end slices over isolated cleverness.

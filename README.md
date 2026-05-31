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
| `bun --silent run mcp` / `npm run --silent mcp` | Start the local stdio MCP server |
| `bun run seed` / `npm run seed` | Create/update the deterministic local demo database |
| `bun run check` / `npm run check` | Compile Python packages and enforce package isolation |
| `bun run eval:ai` / `npm run eval:ai` | Run AI chat and MCP evaluation suite |
| `bun run test:integration` / `npm run test:integration` | Run FastAPI integration tests against isolated SQLite databases |
| `bun run test:e2e` / `npm run test:e2e` | Run the Playwright demo-path smoke test with isolated seeded state |

Today the root launcher starts:

- Core API shell: `http://127.0.0.1:8000`
- Frontend shell: `http://127.0.0.1:5173`

Seed local demo data before exercising API or UI flows:

```bash
bun run seed
```

The seed command writes to SQLite and generated demo storage artifacts. API and frontend work should read this state instead of embedding placeholder data.

## Supervised Commands

The command path is intentionally narrow and auditable:

- `POST /api/v1/agent/commands` parses a free-text command and returns `accepted` or `rejected`
- send `execute: false` to receive a structured plan before applying side effects
- accepted commands can run a market watch, create a simple watch, analyze the dossier, or list recommendations
- external contact actions are rejected by guardrails and should use contact packets plus human validation instead
- the frontend `CommandComposer` plans first, then executes after user validation and refreshes the affected operational views

## AI Chat

The AI chat path keeps provider secrets server-side:

- `GET /api/v1/ai/providers` returns provider availability and model metadata
- `GET/PATCH /api/v1/ai/provider-settings` lets the frontend configure provider secrets
- `POST /api/v1/ai/chat` routes supervised platform commands through the existing agent command path before calling a model provider
- provider API keys are read from environment variables or the encrypted local secret store and are never returned to the frontend
- OpenAI, Anthropic, and Google model lists are fetched from their provider APIs at runtime
- `DOSSIERAGENT_CODEX_PROVIDER_PATH` enables a local Codex-compatible executable for development use

Set these variables on the API process when provider-backed chat should be enabled:

```bash
DOSSIERAGENT_OPENAI_API_KEY=
DOSSIERAGENT_ANTHROPIC_API_KEY=
DOSSIERAGENT_GOOGLE_API_KEY=
DOSSIERAGENT_CODEX_PROVIDER_PATH=
DOSSIERAGENT_CODEX_PROVIDER_MODE=codex_cli
DOSSIERAGENT_AI_TIMEOUT_SECONDS=20
DOSSIERAGENT_SECRET_STORE_PATH=
DOSSIERAGENT_SECRETS_KEY=
DOSSIERAGENT_SECRETS_KEY_PATH=
```

The Settings page writes provider keys to a Fernet-encrypted local store under
`$DOSSIERAGENT_STORAGE_PATH/secrets` by default. File permissions are restricted
to the server user. Environment variables still override stored values, and the
frontend only receives redacted field names such as `stored:api_key`.

## Local MCP

`bun --silent run mcp` starts the local stdio MCP server. It exposes supervised
platform tools through the core HTTP API and keeps credentials in environment
variables:

```bash
DOSSIERAGENT_MCP_API_BASE_URL=http://127.0.0.1:8000/api/v1
DOSSIERAGENT_MCP_DEMO_USER_ID=usr_demo
DOSSIERAGENT_MCP_BEARER_TOKEN=
```

The MCP tool surface does not include autonomous email or external contact
tools. Contact remains a contact-packet plus user-check workflow.

## AI Evaluations

Run deterministic AI feature evaluations from the repository root:

```bash
bun run eval:ai
```

This seeds isolated SQLite state and evaluates:

- AI provider registry response shape without live credentials
- AI chat routing through supervised platform tools
- blocked autonomous external contact in AI chat
- MCP stdio initialize, tool listing, and tool call behavior
- MCP tool exposure guardrails

Live provider smoke is opt-in and reads credentials only from the current
environment or local provider login. For Codex OAuth-backed live smoke:

```bash
DOSSIERAGENT_EVAL_LIVE_PROVIDER=codex \
DOSSIERAGENT_CODEX_PROVIDER_PATH="$(command -v codex)" \
bun run eval:ai -- -m live_provider
```

Do not paste OAuth tokens into `.env`; the Codex CLI reads its own local auth.

## Supabase Auth

Auth is wired through Supabase while preserving the spec API contract:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/password/forgot`
- `POST /api/v1/auth/logout`
- `GET /api/v1/me`

Set these environment variables on the API process to enable Supabase-backed login:

```bash
DOSSIERAGENT_SUPABASE_URL=https://<project-ref>.supabase.co
DOSSIERAGENT_SUPABASE_ANON_KEY=<anon-key>
DOSSIERAGENT_AUTH_REQUIRED=false
```

`DOSSIERAGENT_AUTH_REQUIRED=false` keeps the seed-based local demo usable without a token. Set it to `true` when every `/api/v1/*` user route should require a bearer token. Authenticated Supabase users are provisioned into the local SQLite `users` table on first login or first bearer request; `usr_demo` is only the unauthenticated seeded demo user.

The frontend `/auth` route provides login, register, forgotten-password, and
logout state handling. Register supports both immediate Supabase sessions and
email-confirmation-required responses.

## Browser Import

Manual listing import is available through `POST /api/v1/listings/import-url`.
The route asks `packages/browser` to extract the listing, then `core`
orchestrates normalization, ranking, dedupe, SQLite persistence, and optional
Elastic indexing.

Market watch runs use the same supervised package path. `POST
/api/v1/market-watches/{watch_id}/run-now`, command-triggered scans, and the
cron route read source configuration from SQLite, extract list and detail pages
through the browser package, normalize/dedupe/rank candidates with dossier
context, persist changed listings, optionally index them in Elastic, and create
run events plus a notification. The deterministic seed stores its next-scan
fixture HTML in the watch source config.

The private extraction surface `POST /api/v1/internal/browser/extract` is for
local/internal worker calls only. Configure
`DOSSIERAGENT_BROWSER_INTERNAL_SECRET` when it should require a bearer secret;
without that secret it accepts local calls only.

## Docker Compose

For the full local stack with API, frontend, Elasticsearch, Kibana, and the Playwright worker:

```bash
cp .env.example .env
docker compose up --build
```

The compose stack mounts SQLite and generated files from the repository:

- `./data` -> `/app/data`
- `./storage` -> `/app/storage`

The `seed` service runs the deterministic demo seed before the API starts. To refresh demo data later:

```bash
docker compose run --rm seed
```

Local service URLs:

- Frontend: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Kibana: `http://127.0.0.1:5601`
- Elasticsearch: `http://127.0.0.1:9200`

SQLite is mounted for a single-machine MVP. Do not run multiple API containers or multiple VMs against the same SQLite file.

For VM sizing, Docker setup, backup notes, and the three-minute reviewer demo,
see [docs/DEPLOYMENT_AND_DEMO.md](docs/DEPLOYMENT_AND_DEMO.md).

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
- Listings with manual URL import, duplicate/repost handling, score explanations, risk flags, and user decisions
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

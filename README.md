# DossierAgent

DossierAgent is scaffolded as a package-based monorepo. Each package owns one concern from the specification and is designed to be maintained independently.

## Root Commands

The project is executable from the repository root with either Bun or npm:

```bash
bun run dev
npm run dev
```

Useful commands:

| Command | Purpose |
|---|---|
| `bun run dev` / `npm run dev` | Launch all implemented runtime services from the root supervisor |
| `bun run start` / `npm run start` | Same root supervisor entrypoint for production-style startup |
| `bun run status` / `npm run status` | Show package and service readiness |
| `bun run packages` / `npm run packages` | List package concerns |
| `bun run check` / `npm run check` | Compile Python packages and enforce feature-package isolation |

Package root:

```text
packages/<package_name>
```

Packages:

| Package | Concern |
|---|---|
| `frontend` | Desktop-first command center UI |
| `agent` | Supervised agent commands, runs, tools, and prompt contracts |
| `database` | SQLite schema, migrations, and repositories |
| `search_engine` | Elasticsearch mappings, indexing, and hybrid search |
| `browser` | Playwright extraction worker and source adapters |
| `schedule` | Cron-facing watch scheduling and due-run policy |
| `processing` | Dossier analysis, listing normalization, ranking, dedupe, and contact packet preparation |
| `mcp` | MCP configuration and Elastic Agent Builder integration |
| `core` | Minimal composition layer used to stitch packages together |

The package rule is simple: feature packages do not import each other. They expose a small public manifest or adapter surface, and `core` wires those pieces together at the application boundary.

See [ARCHITECTURE.md](ARCHITECTURE.md) for package ownership boundaries.

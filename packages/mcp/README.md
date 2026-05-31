# `mcp`

Model Context Protocol integration package.

## Owns

- Elastic Agent Builder MCP configuration
- MCP tool exposure policy
- MCP security defaults
- fallback MCP server notes

## Does Not Own

- app-side Elastic query implementation
- ranking algorithms
- SQLite persistence
- frontend checks

## Public Surface

- MCP server configuration builders
- Elastic Agent Builder connection metadata
- allowed MCP tool declarations
- local stdio MCP server for DossierAgent platform tools

## Local DossierAgent MCP Server

Run the local stdio server from the repository root. Use silent mode so stdout
contains only MCP JSON-RPC messages:

```bash
bun --silent run mcp
```

The stdio server speaks JSON-RPC over stdin/stdout and exposes only supervised
DossierAgent tools. It calls the core HTTP API instead of importing feature
packages directly.

Runtime environment:

```bash
DOSSIERAGENT_MCP_API_BASE_URL=http://127.0.0.1:8000/api/v1
DOSSIERAGENT_MCP_DEMO_USER_ID=usr_demo
DOSSIERAGENT_MCP_BEARER_TOKEN=
DOSSIERAGENT_MCP_TIMEOUT_SECONDS=20
```

Tools:

| Tool | Purpose |
|---|---|
| `dossieragent_search_listings` | Listing search summaries |
| `dossieragent_get_listing` | Listing review context |
| `dossieragent_run_watch_now` | Supervised watch run trigger |
| `dossieragent_dossier_readiness` | Dossier readiness snapshot |
| `dossieragent_create_contact_packet` | Contact packet draft for human review |
| `dossieragent_list_user_checks` | Human validation checks |
| `dossieragent_agent_command` | Existing supervised command path |

No MCP tool sends email, calls landlords, bypasses login, or performs external
contact. Contact remains a contact-packet plus human-review workflow.

## Kibana Agent Builder MCP

The primary MCP path is Kibana Agent Builder, exposed at:

```text
{KIBANA_URL}/api/agent_builder/mcp
```

For a Kibana Space, use:

```text
{KIBANA_URL}/s/{space_id}/api/agent_builder/mcp
```

`build_elastic_agent_builder_config()` emits an MCP client config that runs
`mcp-remote` and passes the authorization header through environment variables:

```json
{
  "mcpServers": {
    "elastic-agent-builder": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "${KIBANA_URL}/api/agent_builder/mcp",
        "--header",
        "Authorization:${ELASTIC_MCP_AUTH_HEADER}"
      ],
      "env": {
        "KIBANA_URL": "${KIBANA_URL}",
        "ELASTIC_MCP_AUTH_HEADER": "ApiKey ${ELASTIC_API_KEY}"
      }
    }
  }
}
```

The API key itself must come from the runtime environment. Do not commit a
resolved `Authorization` header or raw Elastic API key.

## Allowed Tools And Index Permissions

DossierAgent should expose only read-only MCP capabilities for the MVP:

| Tool | Purpose | Indices |
|---|---|---|
| `search` | Retrieve matching listings and dossier metadata | `listings_v1`, `documents_v1` |
| `esql` | Run read-only ES\|QL analysis over allowed indices | `listings_v1`, `documents_v1` |
| `get_mappings` | Inspect schemas for allowed indices | `listings_v1`, `documents_v1` |

The corresponding Elasticsearch index privileges are:

| Index | Privileges |
|---|---|
| `listings_v1` | `read`, `view_index_metadata` |
| `documents_v1` | `read`, `view_index_metadata` |

Do not grant write, delete, index-management, cluster-admin, or unrestricted
wildcard privileges to the demo MCP credential.

## Fallback Plan B

`mcp-server-elasticsearch` is a fallback only. Use it only if Kibana Agent
Builder is unavailable because of deployment, version, or license constraints.
It is less credible for the partner MCP demo and should stay limited to read
and inspection tools such as `list_indices`, `get_mappings`, `search`, `esql`,
and `get_shards`.

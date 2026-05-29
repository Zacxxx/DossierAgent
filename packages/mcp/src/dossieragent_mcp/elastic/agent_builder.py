from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

AGENT_BUILDER_SERVER_NAME = "elastic-agent-builder"
DEFAULT_KIBANA_URL_ENV = "KIBANA_URL"
DEFAULT_AUTH_HEADER_ENV = "ELASTIC_MCP_AUTH_HEADER"
DEFAULT_API_KEY_ENV = "ELASTIC_API_KEY"
DEFAULT_INDICES = ("listings_v1", "documents_v1")


@dataclass(frozen=True, slots=True)
class AllowedMcpTool:
    name: str
    purpose: str
    indices: tuple[str, ...]
    read_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IndexPermission:
    index_pattern: str
    privileges: tuple[str, ...] = ("read", "view_index_metadata")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


ALLOWED_MCP_TOOLS = (
    AllowedMcpTool(
        name="search",
        purpose="Read-only listing and dossier retrieval for agent reasoning.",
        indices=DEFAULT_INDICES,
    ),
    AllowedMcpTool(
        name="esql",
        purpose="Read-only ES|QL analysis over allowed DossierAgent indices.",
        indices=DEFAULT_INDICES,
    ),
    AllowedMcpTool(
        name="get_mappings",
        purpose="Schema inspection for allowed DossierAgent indices.",
        indices=DEFAULT_INDICES,
    ),
)

INDEX_PERMISSIONS = tuple(IndexPermission(index_pattern=index) for index in DEFAULT_INDICES)

FALLBACK_MCP_ELASTICSEARCH = {
    "name": "mcp-server-elasticsearch",
    "status": "deprecated_plan_b",
    "allowed_tools": ("list_indices", "get_mappings", "search", "esql", "get_shards"),
    "use_only_when": (
        "Kibana Agent Builder MCP is unavailable because of deployment, version, "
        "or license constraints."
    ),
}


def agent_builder_endpoint(kibana_url_reference: str, *, space_id: str | None = None) -> str:
    base_url = kibana_url_reference.rstrip("/")
    if space_id is None or not space_id.strip():
        return f"{base_url}/api/agent_builder/mcp"
    clean_space_id = space_id.strip().strip("/")
    return f"{base_url}/s/{clean_space_id}/api/agent_builder/mcp"


def build_elastic_agent_builder_config(
    *,
    server_name: str = AGENT_BUILDER_SERVER_NAME,
    kibana_url_env: str = DEFAULT_KIBANA_URL_ENV,
    auth_header_env: str = DEFAULT_AUTH_HEADER_ENV,
    api_key_env: str = DEFAULT_API_KEY_ENV,
    space_id: str | None = None,
) -> dict[str, Any]:
    kibana_url_reference = env_reference(kibana_url_env)
    auth_header_reference = env_reference(auth_header_env)
    api_key_reference = env_reference(api_key_env)

    return {
        "mcpServers": {
            server_name: {
                "command": "npx",
                "args": [
                    "mcp-remote",
                    agent_builder_endpoint(kibana_url_reference, space_id=space_id),
                    "--header",
                    f"Authorization:{auth_header_reference}",
                ],
                "env": {
                    kibana_url_env: kibana_url_reference,
                    auth_header_env: f"ApiKey {api_key_reference}",
                },
            }
        }
    }


def list_allowed_mcp_tools() -> list[dict[str, Any]]:
    return [tool.as_dict() for tool in ALLOWED_MCP_TOOLS]


def list_index_permissions() -> list[dict[str, Any]]:
    return [permission.as_dict() for permission in INDEX_PERMISSIONS]


def fallback_mcp_elasticsearch_policy() -> dict[str, Any]:
    return dict(FALLBACK_MCP_ELASTICSEARCH)


def env_reference(name: str) -> str:
    if not name or not name.strip():
        raise ValueError("Environment variable name is required.")
    return "${" + name.strip() + "}"

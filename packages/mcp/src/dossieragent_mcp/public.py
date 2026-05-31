from .elastic import (
    build_elastic_agent_builder_config,
    fallback_mcp_elasticsearch_policy,
    list_allowed_mcp_tools,
    list_index_permissions,
)
from .tools import list_platform_tools

PACKAGE_MANIFEST = {
    "name": "mcp",
    "concern": "MCP configuration and Elastic Agent Builder integration.",
    "owns": (
        "elastic agent builder mcp config",
        "mcp tool exposure policy",
        "mcp security defaults",
    ),
    "exposes": (
        "build_elastic_agent_builder_config",
        "list_allowed_mcp_tools",
        "list_index_permissions",
        "fallback_mcp_elasticsearch_policy",
        "list_platform_tools",
    ),
    "events": (
        "mcp.config.generated",
    ),
}


def get_manifest() -> dict[str, object]:
    return dict(PACKAGE_MANIFEST)

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
    ),
    "events": (
        "mcp.config.generated",
    ),
}


def get_manifest() -> dict[str, object]:
    return dict(PACKAGE_MANIFEST)


from __future__ import annotations

import unittest

from dossieragent_mcp import (
    build_elastic_agent_builder_config,
    fallback_mcp_elasticsearch_policy,
    list_allowed_mcp_tools,
    list_index_permissions,
)
from dossieragent_mcp.elastic import agent_builder_endpoint


class ElasticAgentBuilderConfigTests(unittest.TestCase):
    def test_default_config_uses_mcp_remote_and_environment_auth(self) -> None:
        config = build_elastic_agent_builder_config()
        server = config["mcpServers"]["elastic-agent-builder"]

        self.assertEqual(server["command"], "npx")
        self.assertEqual(
            server["args"],
            [
                "mcp-remote",
                "${KIBANA_URL}/api/agent_builder/mcp",
                "--header",
                "Authorization:${ELASTIC_MCP_AUTH_HEADER}",
            ],
        )
        self.assertEqual(server["env"]["KIBANA_URL"], "${KIBANA_URL}")
        self.assertEqual(server["env"]["ELASTIC_MCP_AUTH_HEADER"], "ApiKey ${ELASTIC_API_KEY}")

    def test_space_endpoint_variant(self) -> None:
        self.assertEqual(
            agent_builder_endpoint("${KIBANA_URL}", space_id="demo-space"),
            "${KIBANA_URL}/s/demo-space/api/agent_builder/mcp",
        )

    def test_allowed_tools_are_read_only_and_scoped_to_dossieragent_indices(self) -> None:
        tools = list_allowed_mcp_tools()
        self.assertEqual({tool["name"] for tool in tools}, {"search", "esql", "get_mappings"})
        self.assertTrue(all(tool["read_only"] for tool in tools))
        for tool in tools:
            self.assertEqual(tuple(tool["indices"]), ("listings_v1", "documents_v1"))

    def test_index_permissions_are_read_only(self) -> None:
        permissions = list_index_permissions()

        self.assertEqual(
            {permission["index_pattern"] for permission in permissions},
            {"listings_v1", "documents_v1"},
        )
        for permission in permissions:
            self.assertEqual(tuple(permission["privileges"]), ("read", "view_index_metadata"))

    def test_fallback_policy_marks_mcp_elasticsearch_as_plan_b(self) -> None:
        policy = fallback_mcp_elasticsearch_policy()

        self.assertEqual(policy["name"], "mcp-server-elasticsearch")
        self.assertEqual(policy["status"], "deprecated_plan_b")
        self.assertIn("search", policy["allowed_tools"])


if __name__ == "__main__":
    unittest.main()

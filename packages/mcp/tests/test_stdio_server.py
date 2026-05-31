from __future__ import annotations

import json
import unittest
from io import StringIO
from typing import Any

from dossieragent_mcp import DossierAgentMcpServer, list_platform_tools
from dossieragent_mcp.servers.stdio import run_stdio


class FakeInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return {"ok": True, "name": name, "arguments": arguments}


class StdioServerTests(unittest.TestCase):
    def test_tool_list_covers_supervised_platform_surface(self) -> None:
        tools = list_platform_tools()
        names = {tool["name"] for tool in tools}

        self.assertEqual(
            names,
            {
                "dossieragent_search_listings",
                "dossieragent_get_listing",
                "dossieragent_run_watch_now",
                "dossieragent_dossier_readiness",
                "dossieragent_create_contact_packet",
                "dossieragent_list_user_checks",
                "dossieragent_agent_command",
            },
        )
        self.assertFalse(any("email" in name or "send" in name for name in names))

    def test_server_handles_initialize_and_tool_call(self) -> None:
        invoker = FakeInvoker()
        server = DossierAgentMcpServer(invoker=invoker)

        initialize = server.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        self.assertIsNotNone(initialize)
        self.assertEqual(initialize.result["protocolVersion"], "2025-03-26")  # type: ignore[index]
        self.assertIn("tools", initialize.result["capabilities"])  # type: ignore[index]

        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "dossieragent_search_listings",
                    "arguments": {"city": "Toulouse", "limit": 5},
                },
            }
        )

        self.assertIsNotNone(response)
        self.assertIsNone(response.error)
        self.assertEqual(invoker.calls, [("dossieragent_search_listings", {"city": "Toulouse", "limit": 5})])
        self.assertEqual(response.result["structuredContent"]["ok"], True)  # type: ignore[index]

    def test_stdio_loop_reads_jsonrpc_lines(self) -> None:
        invoker = FakeInvoker()
        server = DossierAgentMcpServer(invoker=invoker)
        stdin = StringIO(
            json.dumps({"jsonrpc": "2.0", "id": "1", "method": "tools/list"}) + "\n"
        )
        stdout = StringIO()

        exit_code = run_stdio(server=server, stdin=stdin, stdout=stdout)

        self.assertEqual(exit_code, 0)
        response = json.loads(stdout.getvalue())
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], "1")
        self.assertEqual(response["result"]["tools"][0]["name"], "dossieragent_search_listings")


if __name__ == "__main__":
    unittest.main()

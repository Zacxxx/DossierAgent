from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, TextIO

from dossieragent_mcp.tools.platform import DossierAgentApiInvoker, ToolInvoker, list_platform_tools

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "dossieragent-mcp", "version": "0.1.0"}


@dataclass(slots=True)
class JsonRpcResponse:
    id: str | int
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            payload["error"] = self.error
        else:
            payload["result"] = self.result or {}
        return payload


class DossierAgentMcpServer:
    def __init__(self, invoker: ToolInvoker | None = None) -> None:
        self.invoker = invoker or DossierAgentApiInvoker()

    def handle_request(self, request: dict[str, Any]) -> JsonRpcResponse | None:
        request_id = request.get("id")
        if request_id is None:
            return None
        method = request.get("method")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        try:
            if method == "initialize":
                return JsonRpcResponse(id=request_id, result=self.initialize_result())
            if method == "tools/list":
                return JsonRpcResponse(id=request_id, result={"tools": list_platform_tools()})
            if method == "tools/call":
                return JsonRpcResponse(id=request_id, result=self.call_tool(params))
            if method == "ping":
                return JsonRpcResponse(id=request_id, result={})
            return JsonRpcResponse(
                id=request_id,
                error={"code": -32601, "message": f"Method not found: {method}"},
            )
        except Exception as exc:
            return JsonRpcResponse(
                id=request_id,
                error={
                    "code": -32000,
                    "message": str(exc),
                    "data": {"method": method},
                },
            )

    def initialize_result(self) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        }

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str):
            raise ValueError("tools/call requires params.name.")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValueError("tools/call params.arguments must be an object.")
        payload = self.invoker.invoke(name, arguments)
        text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": payload,
            "isError": False,
        }


def run_stdio(
    *,
    server: DossierAgentMcpServer | None = None,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> int:
    active_server = server or DossierAgentMcpServer()
    for line in stdin:
        raw_line = line.strip()
        if not raw_line:
            continue
        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            response = JsonRpcResponse(
                id=0,
                error={"code": -32700, "message": "Parse error", "data": {"message": str(exc)}},
            )
        else:
            if not isinstance(request, dict):
                response = JsonRpcResponse(
                    id=0,
                    error={"code": -32600, "message": "Invalid Request"},
                )
            else:
                response = active_server.handle_request(request)
        if response is not None:
            stdout.write(json.dumps(response.as_dict(), ensure_ascii=True, separators=(",", ":")))
            stdout.write("\n")
            stdout.flush()
    return 0


def main() -> int:
    return run_stdio()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode
from uuid import uuid4


class ToolInvoker(Protocol):
    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a DossierAgent platform tool."""


@dataclass(frozen=True, slots=True)
class PlatformTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    sensitive: bool = False

    def as_mcp_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


PLATFORM_TOOLS: tuple[PlatformTool, ...] = (
    PlatformTool(
        name="dossieragent_search_listings",
        description="Search listing summaries through the DossierAgent API.",
        input_schema={
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "status": {"type": "string"},
                "city": {"type": "string"},
                "district": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "additionalProperties": False,
        },
    ),
    PlatformTool(
        name="dossieragent_get_listing",
        description="Get listing review context, source links, images, reasons, and risks.",
        input_schema={
            "type": "object",
            "required": ["listing_id"],
            "properties": {"listing_id": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    PlatformTool(
        name="dossieragent_run_watch_now",
        description="Trigger a supervised market-watch run. No external contact is performed.",
        sensitive=True,
        input_schema={
            "type": "object",
            "required": ["watch_id"],
            "properties": {
                "watch_id": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    PlatformTool(
        name="dossieragent_dossier_readiness",
        description="Read the current dossier readiness snapshot.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    PlatformTool(
        name="dossieragent_create_contact_packet",
        description="Prepare a contact packet for human review. The tool never sends messages.",
        sensitive=True,
        input_schema={
            "type": "object",
            "required": ["listing_id"],
            "properties": {
                "listing_id": {"type": "string"},
                "language": {"type": "string"},
                "tone": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    PlatformTool(
        name="dossieragent_list_user_checks",
        description="List pending or recent human validation checks.",
        input_schema={
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    PlatformTool(
        name="dossieragent_agent_command",
        description="Run the supervised agent command parser and execution path.",
        sensitive=True,
        input_schema={
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {"type": "string"},
                "execute": {"type": "boolean"},
                "context": {"type": "object"},
            },
            "additionalProperties": False,
        },
    ),
)


class DossierAgentApiInvoker:
    def __init__(
        self,
        *,
        api_base_url: str | None = None,
        demo_user_id: str | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_base_url = (api_base_url or os.environ.get("DOSSIERAGENT_MCP_API_BASE_URL") or "http://127.0.0.1:8000/api/v1").rstrip("/")
        self.demo_user_id = demo_user_id or os.environ.get("DOSSIERAGENT_MCP_DEMO_USER_ID")
        self.bearer_token = bearer_token or os.environ.get("DOSSIERAGENT_MCP_BEARER_TOKEN")
        self.timeout_seconds = timeout_seconds or float(os.environ.get("DOSSIERAGENT_MCP_TIMEOUT_SECONDS", "20"))

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "dossieragent_search_listings":
            return self._get("/listings", query=clean_query(arguments, {"q", "status", "city", "district", "limit"}))
        if name == "dossieragent_get_listing":
            return self._get(f"/listings/{required_argument(arguments, 'listing_id')}")
        if name == "dossieragent_run_watch_now":
            idempotency_key = str(arguments.get("idempotency_key") or f"mcp_{uuid4().hex}")
            return self._post(
                f"/market-watches/{required_argument(arguments, 'watch_id')}/run-now",
                payload={},
                headers={"Idempotency-Key": idempotency_key},
            )
        if name == "dossieragent_dossier_readiness":
            return self._get("/dossier/readiness")
        if name == "dossieragent_create_contact_packet":
            return self._post(
                "/contact-packets",
                payload={
                    "listing_id": required_argument(arguments, "listing_id"),
                    "language": str(arguments.get("language") or "fr"),
                    "tone": str(arguments.get("tone") or "polite_direct"),
                },
            )
        if name == "dossieragent_list_user_checks":
            return self._get("/user-checks", query=clean_query(arguments, {"status"}))
        if name == "dossieragent_agent_command":
            return self._post(
                "/agent/commands",
                payload={
                    "command": required_argument(arguments, "command"),
                    "execute": bool(arguments.get("execute", True)),
                    "context": arguments.get("context") if isinstance(arguments.get("context"), dict) else {},
                },
            )
        raise KeyError(f"Unknown DossierAgent MCP tool: {name}")

    def _get(self, path: str, *, query: dict[str, Any] | None = None) -> dict[str, Any]:
        suffix = f"?{urlencode(query)}" if query else ""
        return self._request("GET", f"{path}{suffix}")

    def _post(
        self,
        path: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._request("POST", path, payload=payload, headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {"Accept": "application/json", **(headers or {})}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        if self.demo_user_id:
            request_headers["X-Demo-User-Id"] = self.demo_user_id
        if self.bearer_token:
            request_headers["Authorization"] = f"Bearer {self.bearer_token}"
        request = urllib.request.Request(
            f"{self.api_base_url}{path}",
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DossierAgent API returned HTTP {exc.code}: {body}") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("DossierAgent API returned a non-object JSON payload.")
        return decoded


def list_platform_tools() -> list[dict[str, Any]]:
    return [tool.as_mcp_tool() for tool in PLATFORM_TOOLS]


def clean_query(arguments: dict[str, Any], allowed_keys: set[str]) -> dict[str, Any]:
    return {
        key: value
        for key, value in arguments.items()
        if key in allowed_keys and value is not None and value != ""
    }


def required_argument(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required argument: {key}")
    return value.strip()

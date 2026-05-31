from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from dossieragent_core.api import create_app
from dossieragent_database import create_connection
from dossieragent_database.seed import seed_demo_data
from dossieragent_mcp import DossierAgentMcpServer, list_platform_tools
from dossieragent_mcp.servers.stdio import run_stdio
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    database_path = tmp_path / "dossieragent.db"
    storage_path = tmp_path / "storage"
    connection = create_connection(database_path)
    try:
        seed_demo_data(connection, storage_path=storage_path)
    finally:
        connection.close()

    env = {
        "DOSSIERAGENT_SQLITE_PATH": str(database_path),
        "DOSSIERAGENT_STORAGE_PATH": str(storage_path),
        "DOSSIERAGENT_ELASTIC_URL": "",
    }
    with patch.dict(os.environ, env):
        with TestClient(create_app()) as test_client:
            yield test_client


def test_ai_chat_provider_registry_shape_without_live_credentials(client: TestClient) -> None:
    with patch.dict(
        os.environ,
        {
            "DOSSIERAGENT_OPENAI_API_KEY": "",
            "DOSSIERAGENT_ANTHROPIC_API_KEY": "",
            "DOSSIERAGENT_GOOGLE_API_KEY": "",
            "DOSSIERAGENT_CODEX_PROVIDER_PATH": "",
        },
    ):
        response = client.get("/api/v1/ai/providers")

    assert response.status_code == 200
    payload = response.json()
    providers = {provider["id"]: provider for provider in payload["providers"]}
    assert set(providers) == {"openai", "anthropic", "google", "codex"}
    assert all("models" in provider for provider in providers.values())
    assert "access_token" not in json.dumps(payload)
    assert "refresh_token" not in json.dumps(payload)


def test_ai_chat_routes_supervised_listing_command(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ai/chat",
        json={
            "provider": "openai",
            "model": "tool-router",
            "messages": [{"role": "user", "content": "Affiche les annonces recommandees"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "dossieragent_tools"
    assert payload["tool_call"]["status"] == "accepted"
    assert payload["tool_call"]["intent"] == "show_recommended_listings"
    assert payload["tool_call"]["result"]["type"] == "listing_collection"
    assert len(payload["tool_call"]["result"]["items"]) >= 4


def test_ai_chat_blocks_autonomous_external_contact(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ai/chat",
        json={
            "provider": "openai",
            "model": "tool-router",
            "messages": [{"role": "user", "content": "Envoie un email au proprietaire"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "dossieragent_tools"
    assert payload["tool_call"]["status"] == "rejected"
    assert payload["tool_call"]["intent"] == "blocked_external_contact"
    assert "no_autonomous_email" in payload["tool_call"]["guardrails"]


def test_mcp_tool_surface_has_required_tools_and_no_external_contact_tool() -> None:
    tools = list_platform_tools()
    names = {tool["name"] for tool in tools}

    assert {
        "dossieragent_search_listings",
        "dossieragent_get_listing",
        "dossieragent_run_watch_now",
        "dossieragent_dossier_readiness",
        "dossieragent_create_contact_packet",
        "dossieragent_list_user_checks",
        "dossieragent_agent_command",
    }.issubset(names)
    assert not any("email" in name or "send" in name or "landlord" in name for name in names)


def test_mcp_stdio_initialize_tools_list_and_tool_call() -> None:
    class FakeInvoker:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def invoke(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
            self.calls.append((name, arguments))
            return {"ok": True, "name": name, "arguments": arguments}

    invoker = FakeInvoker()
    server = DossierAgentMcpServer(invoker=invoker)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {}}),
                json.dumps({"jsonrpc": "2.0", "id": "list", "method": "tools/list", "params": {}}),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "call",
                        "method": "tools/call",
                        "params": {
                            "name": "dossieragent_search_listings",
                            "arguments": {"city": "Toulouse", "limit": 3},
                        },
                    }
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    assert run_stdio(server=server, stdin=stdin, stdout=stdout) == 0
    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["result"]["capabilities"]["tools"]["listChanged"] is False
    assert responses[1]["result"]["tools"][0]["name"] == "dossieragent_search_listings"
    assert responses[2]["result"]["structuredContent"]["ok"] is True
    assert invoker.calls == [("dossieragent_search_listings", {"city": "Toulouse", "limit": 3})]


@pytest.mark.live_provider
def test_live_provider_chat_smoke(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = os.environ.get("DOSSIERAGENT_EVAL_LIVE_PROVIDER", "").strip().lower()
    if not provider:
        pytest.skip("Set DOSSIERAGENT_EVAL_LIVE_PROVIDER=codex/openai/anthropic/google to run live.")

    if provider == "codex" and not os.environ.get("DOSSIERAGENT_CODEX_PROVIDER_PATH"):
        codex_path = shutil.which("codex")
        if not codex_path:
            pytest.skip("Codex CLI is not installed.")
        monkeypatch.setenv("DOSSIERAGENT_CODEX_PROVIDER_PATH", codex_path)
        monkeypatch.setenv("DOSSIERAGENT_CODEX_PROVIDER_MODE", "codex_cli")

    model = os.environ.get("DOSSIERAGENT_EVAL_LIVE_MODEL", "codex-default")
    response = client.post(
        "/api/v1/ai/chat",
        json={
            "provider": provider,
            "model": model,
            "use_tools": False,
            "messages": [
                {
                    "role": "user",
                    "content": "Reply with exactly: DOSSIERAGENT_AI_EVAL_READY",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == provider
    assert payload["message"]["content"].strip()
    assert "access_token" not in json.dumps(payload)
    assert "refresh_token" not in json.dumps(payload)

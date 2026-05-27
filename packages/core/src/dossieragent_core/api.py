from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


PACKAGE_STATUS: tuple[dict[str, str], ...] = (
    {"name": "frontend", "concern": "Desktop command center UI"},
    {"name": "agent", "concern": "Supervised commands, runs, tools, and prompt contracts"},
    {"name": "database", "concern": "SQLite schema, migrations, and repositories"},
    {"name": "search_engine", "concern": "Elasticsearch mappings, indexing, and hybrid search"},
    {"name": "browser", "concern": "Playwright extraction worker and source adapters"},
    {"name": "schedule", "concern": "Cron-facing watch scheduling and due-run policy"},
    {"name": "processing", "concern": "Dossier, listing, and contact-packet processing"},
    {"name": "mcp", "concern": "MCP configuration and Elastic Agent Builder integration"},
    {"name": "core", "concern": "Minimal composition and orchestration layer"},
)


class DossierAgentApiHandler(BaseHTTPRequestHandler):
    server_version = "DossierAgentCore/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self.write_json({"status": "ok", "service": "dossieragent-core"})
            return
        if path == "/api/v1/status":
            self.write_json(
                {
                    "status": "bootstrapped",
                    "message": "DossierAgent core API shell is running.",
                    "packages": PACKAGE_STATUS,
                }
            )
            return
        if path in {"/", "/api/v1"}:
            self.write_json(
                {
                    "name": "DossierAgent API",
                    "version": "0.1.0",
                    "health": "/health",
                    "status": "/api/v1/status",
                }
            )
            return
        self.write_json(
            {
                "error": {
                    "code": "not_found",
                    "message": "Route not found.",
                    "details": {"path": path},
                    "trace_id": "dev-shell",
                    "retryable": False,
                }
            },
            status=HTTPStatus.NOT_FOUND,
        )

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.write_common_headers("application/json")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[core-api] {self.address_string()} - {format % args}")

    def write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.write_common_headers("application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_common_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DossierAgent core API shell.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DossierAgentApiHandler)
    print(f"[core-api] listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()


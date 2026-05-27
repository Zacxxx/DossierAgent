from __future__ import annotations

import argparse
import json
import os
from typing import Any
from uuid import uuid4

import uvicorn
from dossieragent_database import build_repositories, create_connection, run_migrations
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


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
DEFAULT_DEMO_USER_ID = "usr_demo"


def create_app() -> FastAPI:
    app = FastAPI(
        title="DossierAgent API",
        version="0.1.0",
        description="Supervised housing-search and rental dossier command center API.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(app)
    install_routes(app)
    return app


def install_routes(app: FastAPI) -> None:
    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "dossieragent-core"}

    @app.get("/api/v1/status", tags=["system"])
    def status() -> dict[str, Any]:
        return {
            "status": "running",
            "api_version": "v1",
            "packages": PACKAGE_STATUS,
        }

    @app.get("/api/v1", tags=["system"])
    def api_root() -> dict[str, str]:
        return {
            "name": "DossierAgent API",
            "version": "0.1.0",
            "health": "/health",
            "status": "/api/v1/status",
        }

    @app.get("/api/v1/dashboard", tags=["dashboard"])
    def dashboard(
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = x_demo_user_id or os.environ.get("DOSSIERAGENT_DEMO_USER_ID", DEFAULT_DEMO_USER_ID)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            payload = build_dashboard_payload(repositories.dashboard, user_id)
        finally:
            connection.close()

        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "dashboard_not_ready",
                    "message": "Dashboard data not found. Run `bun run seed` first.",
                    "details": {"user_id": user_id},
                    "retryable": False,
                },
            )
        return payload


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = str(detail.get("code", status_code_to_error_code(exc.status_code)))
        message = str(detail.get("message", exc.detail if isinstance(exc.detail, str) else "Request failed."))
        details = detail.get("details", {})
        retryable = bool(detail.get("retryable", False))
        return error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details if isinstance(details, dict) else {"details": details},
            retryable=retryable,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            status_code=422,
            code="validation_error",
            message="Parametres invalides.",
            details={"errors": exc.errors()},
            retryable=False,
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, _exc: HTTPException) -> JSONResponse:
        return error_response(
            status_code=404,
            code="not_found",
            message="Route introuvable.",
            details={"path": request.url.path},
            retryable=False,
        )


def build_dashboard_payload(dashboard_repository: Any, user_id: str) -> dict[str, Any] | None:
    current_watch = dashboard_repository.current_watch(user_id)
    latest_run = dashboard_repository.latest_run(user_id)
    dossier_snapshot = dashboard_repository.latest_dossier_snapshot(user_id)
    if current_watch is None or latest_run is None or dossier_snapshot is None:
        return None

    return {
        "current_watch": {
            "id": current_watch["id"],
            "name": current_watch["name"],
            "status": current_watch["status"],
            "next_run_at": current_watch["next_run_at"],
            "last_run_at": current_watch["last_run_at"],
        },
        "latest_run": {
            "id": latest_run["id"],
            "status": latest_run["status"],
            "stats": json_field(latest_run["summary_json"], {}),
            "completed_at": latest_run["completed_at"],
        },
        "dossier": {
            "readiness_score": dossier_snapshot["readiness_score"],
            "can_contact": bool(dossier_snapshot["can_contact"]),
            "can_send_full_dossier": bool(dossier_snapshot["can_send_full_dossier"]),
            "missing_docs": json_field(dossier_snapshot["missing_documents_json"], []),
            "valid_docs": json_field(dossier_snapshot["valid_documents_json"], []),
            "recommendations": json_field(dossier_snapshot["recommendations_json"], []),
        },
        "pending_checks": dashboard_repository.count("user_checks", user_id, "status = 'pending'"),
        "notifications_unread": dashboard_repository.count("notifications", user_id, "read_at IS NULL"),
        "recommended_listings": [
            {
                "id": listing["id"],
                "title": listing["title"],
                "city": listing["city"],
                "district": listing["district"],
                "price": listing["price"],
                "currency": listing["currency"],
                "surface": listing["surface"],
                "rooms": listing["rooms"],
                "status": listing["status"],
                "fit_score": listing["fit_score"],
                "fit_level": listing["fit_level"],
                "risk_flags": json_field(listing["risk_flags_json"], []),
                "explanation": json_field(listing["explanation_json"], []),
            }
            for listing in dashboard_repository.recommended_listings(user_id)
        ],
    }


def json_field(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "trace_id": f"trc_{uuid4().hex[:12]}",
                "retryable": retryable,
            }
        },
    )


def status_code_to_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        500: "internal_error",
    }.get(status_code, "request_failed")


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DossierAgent FastAPI app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

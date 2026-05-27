from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import uvicorn
from dossieragent_database import build_repositories, create_connection, run_migrations
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


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


class CriteriaCreateRequest(BaseModel):
    mode: str
    cities: list[str] = Field(min_length=1)
    districts: list[str] = Field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    surface_min: float | None = None
    rooms_min: float | None = None
    languages: list[str] = Field(default_factory=lambda: ["fr"])
    filters: dict[str, Any] = Field(default_factory=dict)


class MarketWatchCreateRequest(BaseModel):
    criteria_id: str
    name: str
    status: str = "active"
    frequency: str
    next_run_at: str | None = None
    source_config: dict[str, Any] = Field(default_factory=dict)


class MarketWatchPatchRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    frequency: str | None = None
    next_run_at: str | None = None
    source_config: dict[str, Any] | None = None


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
        user_id = request_user_id(x_demo_user_id)
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

    @app.post("/api/v1/criteria", status_code=201, tags=["criteria"])
    def create_criteria(
        request: CriteriaCreateRequest,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        now = utc_now()
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            ensure_user_exists(repositories, user_id)
            row = repositories.search_criteria.create(
                {
                    "id": new_id("crit"),
                    "user_id": user_id,
                    "mode": request.mode,
                    "cities_json": json_data(request.cities),
                    "districts_json": json_data(request.districts),
                    "budget_min": request.budget_min,
                    "budget_max": request.budget_max,
                    "surface_min": request.surface_min,
                    "rooms_min": request.rooms_min,
                    "languages_json": json_data(request.languages),
                    "filters_json": json_data(request.filters),
                    "created_at": now,
                    "updated_at": now,
                }
            )
            connection.commit()
            return criteria_response(row)
        finally:
            connection.close()

    @app.get("/api/v1/criteria", tags=["criteria"])
    def list_criteria(
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            rows = repositories.search_criteria.list_by_user(user_id)
            return {"items": [criteria_response(row) for row in rows]}
        finally:
            connection.close()

    @app.post("/api/v1/market-watches", status_code=201, tags=["market-watches"])
    def create_market_watch(
        request: MarketWatchCreateRequest,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        now = utc_now()
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            ensure_user_exists(repositories, user_id)
            criteria = repositories.search_criteria.find(request.criteria_id)
            if criteria is None or criteria["user_id"] != user_id:
                raise resource_not_found("criteria_not_found", "Critere introuvable.", "criteria_id", request.criteria_id)

            row = repositories.market_watches.create(
                {
                    "id": new_id("watch"),
                    "user_id": user_id,
                    "criteria_id": request.criteria_id,
                    "name": request.name,
                    "status": request.status,
                    "frequency": request.frequency,
                    "next_run_at": request.next_run_at,
                    "last_run_at": None,
                    "source_config_json": json_data(request.source_config),
                    "created_at": now,
                    "updated_at": now,
                }
            )
            connection.commit()
            return market_watch_response(row)
        finally:
            connection.close()

    @app.get("/api/v1/market-watches", tags=["market-watches"])
    def list_market_watches(
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            rows = repositories.market_watches.list_by_user(user_id)
            return {"items": [market_watch_response(row) for row in rows]}
        finally:
            connection.close()

    @app.patch("/api/v1/market-watches/{watch_id}", tags=["market-watches"])
    def update_market_watch(
        watch_id: str,
        request: MarketWatchPatchRequest,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            existing = repositories.market_watches.find(watch_id)
            if existing is None or existing["user_id"] != user_id:
                raise resource_not_found("market_watch_not_found", "Veille introuvable.", "watch_id", watch_id)

            update_data: dict[str, Any] = {"updated_at": utc_now()}
            if request.name is not None:
                update_data["name"] = request.name
            if request.status is not None:
                update_data["status"] = request.status
            if request.frequency is not None:
                update_data["frequency"] = request.frequency
            if request.next_run_at is not None:
                update_data["next_run_at"] = request.next_run_at
            if request.source_config is not None:
                update_data["source_config_json"] = json_data(request.source_config)

            row = repositories.market_watches.update(watch_id, update_data)
            connection.commit()
            return market_watch_response(row)
        finally:
            connection.close()


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


def criteria_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "mode": row["mode"],
        "cities": json_field(row["cities_json"], []),
        "districts": json_field(row["districts_json"], []),
        "budget_min": row["budget_min"],
        "budget_max": row["budget_max"],
        "surface_min": row["surface_min"],
        "rooms_min": row["rooms_min"],
        "languages": json_field(row["languages_json"], ["fr"]),
        "filters": json_field(row["filters_json"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def market_watch_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "criteria_id": row["criteria_id"],
        "name": row["name"],
        "status": row["status"],
        "frequency": row["frequency"],
        "next_run_at": row["next_run_at"],
        "last_run_at": row["last_run_at"],
        "source_config": json_field(row["source_config_json"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def ensure_user_exists(repositories: Any, user_id: str) -> None:
    if repositories.users.find(user_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "user_not_found",
                "message": "Utilisateur demo introuvable. Run `bun run seed` first.",
                "details": {"user_id": user_id},
                "retryable": False,
            },
        )


def resource_not_found(code: str, message: str, field_name: str, field_value: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": code,
            "message": message,
            "details": {field_name: field_value},
            "retryable": False,
        },
    )


def request_user_id(header_user_id: str | None) -> str:
    return header_user_id or os.environ.get("DOSSIERAGENT_DEMO_USER_ID", DEFAULT_DEMO_USER_ID)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def json_data(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


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

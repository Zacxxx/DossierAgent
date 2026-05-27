from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import uvicorn
from dossieragent_database import build_repositories, create_connection, run_migrations
from dossieragent_schedule import compute_next_run_at, find_due_watches
from dossieragent_search_engine import build_listing_search_query
from fastapi import FastAPI, Header, HTTPException, Query, Request
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
LOCAL_CRON_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
VALID_LISTING_STATUSES = {
    "new",
    "saved",
    "recommended",
    "rejected",
    "duplicate",
    "repost",
    "trash",
    "archived",
}


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


class ListingPatchRequest(BaseModel):
    status: str | None = None


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

    @app.post("/api/v1/market-watches/{watch_id}/run-now", status_code=202, tags=["agent-runs"])
    def run_market_watch_now(
        watch_id: str,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        clean_idempotency_key = normalize_optional_header(idempotency_key)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            ensure_user_exists(repositories, user_id)

            if clean_idempotency_key is not None:
                existing_key = repositories.idempotency_keys.find_key(
                    user_id=user_id,
                    scope="run_now",
                    idempotency_key=clean_idempotency_key,
                )
                if existing_key is not None:
                    existing_run = repositories.agent_runs.find(existing_key["resource_id"])
                    if existing_run is not None and existing_run["user_id"] == user_id:
                        return run_now_response(existing_run, idempotent_replay=True)

            watch = repositories.market_watches.find(watch_id)
            if watch is None or watch["user_id"] != user_id:
                raise resource_not_found("market_watch_not_found", "Veille introuvable.", "watch_id", watch_id)

            active_run = repositories.agent_runs.active_for_watch(user_id=user_id, watch_id=watch_id)
            if active_run is not None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "run_already_active",
                        "message": "Un run est deja actif pour cette veille.",
                        "details": {"watch_id": watch_id, "run_id": active_run["id"]},
                        "retryable": True,
                    },
                )

            now = utc_now()
            run = create_agent_run(
                repositories,
                user_id=user_id,
                watch_id=watch_id,
                trigger_type="manual",
                now=now,
            )
            if clean_idempotency_key is not None:
                repositories.idempotency_keys.create(
                    {
                        "id": new_id("idem"),
                        "user_id": user_id,
                        "scope": "run_now",
                        "idempotency_key": clean_idempotency_key,
                        "resource_type": "agent_run",
                        "resource_id": run["id"],
                        "created_at": now,
                    }
                )
            repositories.market_watches.update(
                watch_id,
                {
                    "last_run_at": now,
                    "updated_at": now,
                },
            )
            connection.commit()
            return run_now_response(run, idempotent_replay=False)
        finally:
            connection.close()

    @app.get("/api/v1/agent-runs/{run_id}", tags=["agent-runs"])
    def get_agent_run(
        run_id: str,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            run = repositories.agent_runs.find(run_id)
            if run is None or run["user_id"] != user_id:
                raise resource_not_found("agent_run_not_found", "Run introuvable.", "run_id", run_id)
            return agent_run_response(run)
        finally:
            connection.close()

    @app.get("/api/v1/agent-runs/{run_id}/events", tags=["agent-runs"])
    def get_agent_run_events(
        run_id: str,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            run = repositories.agent_runs.find(run_id)
            if run is None or run["user_id"] != user_id:
                raise resource_not_found("agent_run_not_found", "Run introuvable.", "run_id", run_id)
            return {
                "items": [
                    agent_event_response(event)
                    for event in repositories.agent_events.list_for_run(run_id)
                    if event["user_id"] == user_id
                ]
            }
        finally:
            connection.close()

    @app.get("/api/v1/listings", tags=["listings"])
    def list_listings(
        q: str | None = None,
        status: str | None = None,
        city: str | None = None,
        district: str | None = None,
        watch_id: str | None = None,
        max_price: float | None = None,
        min_price: float | None = None,
        min_surface: float | None = None,
        min_score: float | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = None,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        offset = cursor_to_offset(cursor)
        filters = clean_listing_filters(
            {
                "q": q,
                "status": status,
                "city": city,
                "district": district,
                "watch_id": watch_id,
                "max_price": max_price,
                "min_price": min_price,
                "min_surface": min_surface,
                "min_score": min_score,
            }
        )
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            rows, total, source = search_listing_rows(
                repositories,
                user_id=user_id,
                filters=filters,
                limit=limit,
                offset=offset,
            )
            next_offset = offset + len(rows)
            return {
                "items": [listing_summary_response(row) for row in rows],
                "next_cursor": str(next_offset) if next_offset < total else None,
                "total": total,
                "source": source,
                "filters": filters,
            }
        finally:
            connection.close()

    @app.get("/api/v1/listings/{listing_id}", tags=["listings"])
    def get_listing(
        listing_id: str,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            row = repositories.listings.find_for_user(user_id=user_id, listing_id=listing_id)
            if row is None:
                raise resource_not_found("listing_not_found", "Annonce introuvable.", "listing_id", listing_id)
            return listing_detail_response(row)
        finally:
            connection.close()

    @app.patch("/api/v1/listings/{listing_id}", tags=["listings"])
    def update_listing_decision(
        listing_id: str,
        request: ListingPatchRequest,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            existing = repositories.listings.find_for_user(user_id=user_id, listing_id=listing_id)
            if existing is None:
                raise resource_not_found("listing_not_found", "Annonce introuvable.", "listing_id", listing_id)

            update_data: dict[str, Any] = {"updated_at": utc_now()}
            if request.status is not None:
                if request.status not in VALID_LISTING_STATUSES:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": "invalid_listing_status",
                            "message": "Statut d'annonce invalide.",
                            "details": {
                                "status": request.status,
                                "allowed": sorted(VALID_LISTING_STATUSES),
                            },
                            "retryable": False,
                        },
                    )
                update_data["status"] = request.status

            row = repositories.listings.update(listing_id, update_data)
            connection.commit()
            return listing_detail_response(row)
        finally:
            connection.close()

    @app.post("/api/v1/internal/cron/run-due-watches", tags=["internal"])
    def run_due_watches_from_cron(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any]:
        guard = authorize_cron_request(request, authorization)
        now = utc_now()
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            watches = list_all_market_watches(connection)
            due_watches = find_due_watches(watches, now=now)
            started_runs: list[dict[str, Any]] = []
            skipped_watches: list[dict[str, Any]] = []

            for watch in due_watches:
                active_run = repositories.agent_runs.active_for_watch(
                    user_id=watch["user_id"],
                    watch_id=watch["id"],
                )
                if active_run is not None:
                    skipped_watches.append(
                        {
                            "watch_id": watch["id"],
                            "reason": "run_already_active",
                            "run_id": active_run["id"],
                        }
                    )
                    continue

                try:
                    next_run_at = compute_next_run_at(str(watch["frequency"]), from_time=now)
                except ValueError as exc:
                    skipped_watches.append(
                        {
                            "watch_id": watch["id"],
                            "reason": "unsupported_frequency",
                            "message": str(exc),
                        }
                    )
                    continue

                run = create_agent_run(
                    repositories,
                    user_id=watch["user_id"],
                    watch_id=watch["id"],
                    trigger_type="cron",
                    now=now,
                )
                repositories.market_watches.update(
                    watch["id"],
                    {
                        "last_run_at": now,
                        "next_run_at": next_run_at,
                        "updated_at": now,
                    },
                )
                started_runs.append(
                    {
                        "run_id": run["id"],
                        "watch_id": watch["id"],
                        "status": run["status"],
                        "next_run_at": next_run_at,
                    }
                )

            connection.commit()
            return {
                "status": "ok",
                "guard": guard,
                "now": now,
                "due_count": len(due_watches),
                "started_count": len(started_runs),
                "skipped_count": len(skipped_watches),
                "runs": started_runs,
                "skipped": skipped_watches,
            }
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


def run_now_response(row: dict[str, Any], *, idempotent_replay: bool) -> dict[str, Any]:
    return {
        "run_id": row["id"],
        "status": row["status"],
        "summary": json_field(row["summary_json"], {}),
        "idempotent_replay": idempotent_replay,
    }


def agent_run_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "watch_id": row["watch_id"],
        "trigger_type": row["trigger_type"],
        "intent": row["intent"],
        "status": row["status"],
        "current_step": row["current_step"],
        "summary": json_field(row["summary_json"], {}),
        "error": json_field(row["error_json"], None),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }


def agent_event_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "type": row["type"],
        "severity": row["severity"],
        "message": row["message"],
        "payload": json_field(row["payload_json"], {}),
        "created_at": row["created_at"],
    }


def listing_summary_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id") or row.get("listing_id"),
        "watch_id": row.get("watch_id"),
        "title": row["title"],
        "city": row.get("city"),
        "district": row.get("district"),
        "price": row.get("price"),
        "currency": row.get("currency", "EUR"),
        "surface": row.get("surface"),
        "rooms": row.get("rooms"),
        "status": row["status"],
        "fit_score": row.get("fit_score"),
        "fit_level": row.get("fit_level"),
        "risk_flags": json_field(row.get("risk_flags_json"), row.get("risk_flags", [])),
        "explanation": json_field(row.get("explanation_json"), row.get("explanation", [])),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
    }


def listing_detail_response(row: dict[str, Any]) -> dict[str, Any]:
    payload = listing_summary_response(row)
    payload.update(
        {
            "source": row["source"],
            "source_url": row["source_url"],
            "canonical_url": row["canonical_url"],
            "source_listing_id": row.get("source_listing_id"),
            "description": row.get("description"),
            "postal_code": row.get("postal_code"),
            "agency_name": row.get("agency_name"),
            "contact_hint": row.get("contact_hint"),
            "duplicate_of_listing_id": row.get("duplicate_of_listing_id"),
            "raw_payload": json_field(row.get("raw_payload_json"), row.get("raw_payload", {})),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
    )
    return payload


def empty_run_summary() -> dict[str, int]:
    return {
        "scanned_candidates": 0,
        "new_listings": 0,
        "duplicates": 0,
        "reposts": 0,
        "strong_matches": 0,
    }


def create_agent_run(
    repositories: Any,
    *,
    user_id: str,
    watch_id: str,
    trigger_type: str,
    now: str,
) -> dict[str, Any]:
    run_id = new_id("run")
    run = repositories.agent_runs.create(
        {
            "id": run_id,
            "user_id": user_id,
            "watch_id": watch_id,
            "trigger_type": trigger_type,
            "intent": "run_market_watch",
            "status": "running",
            "current_step": "accepted",
            "summary_json": json_data(empty_run_summary()),
            "error_json": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
    )
    repositories.agent_events.create(
        {
            "id": new_id("evt"),
            "run_id": run_id,
            "user_id": user_id,
            "type": "run_accepted",
            "severity": "info",
            "message": accepted_run_message(trigger_type),
            "payload_json": json_data({"watch_id": watch_id, "trigger_type": trigger_type}),
            "created_at": now,
        }
    )
    repositories.agent_events.create(
        {
            "id": new_id("evt"),
            "run_id": run_id,
            "user_id": user_id,
            "type": "worker_pending",
            "severity": "warning",
            "message": "Worker browser/processing en attente de connexion.",
            "payload_json": json_data({"required_packages": ["browser", "processing"]}),
            "created_at": now,
        }
    )
    return run


def accepted_run_message(trigger_type: str) -> str:
    if trigger_type == "cron":
        return "Run planifie accepte."
    return "Run manuel accepte."


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


def normalize_optional_header(value: str | None) -> str | None:
    if value is None:
        return None
    stripped_value = value.strip()
    return stripped_value or None


def clean_listing_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.strip() if isinstance(value, str) else value
        for key, value in filters.items()
        if value is not None and (not isinstance(value, str) or value.strip())
    }


def cursor_to_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        offset = int(cursor)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_cursor",
                "message": "Curseur de pagination invalide.",
                "details": {"cursor": cursor},
                "retryable": False,
            },
        ) from exc
    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_cursor",
                "message": "Curseur de pagination invalide.",
                "details": {"cursor": cursor},
                "retryable": False,
            },
        )
    return offset


def search_listing_rows(
    repositories: Any,
    *,
    user_id: str,
    filters: dict[str, Any],
    limit: int,
    offset: int,
) -> tuple[tuple[dict[str, Any], ...], int, str]:
    elastic_rows = search_elastic_listings(
        user_id=user_id,
        filters=filters,
        limit=limit,
        offset=offset,
    )
    if elastic_rows is not None:
        return elastic_rows[0], elastic_rows[1], "elastic"

    rows, total = repositories.listings.search(
        user_id=user_id,
        filters=filters,
        limit=limit,
        offset=offset,
    )
    return rows, total, "sqlite"


def search_elastic_listings(
    *,
    user_id: str,
    filters: dict[str, Any],
    limit: int,
    offset: int,
) -> tuple[tuple[dict[str, Any], ...], int] | None:
    elastic_url = normalize_optional_header(os.environ.get("DOSSIERAGENT_ELASTIC_URL"))
    if elastic_url is None:
        return None

    index_name = os.environ.get("DOSSIERAGENT_ELASTIC_LISTINGS_INDEX", "listings_v1")
    query = build_listing_search_query(user_id=user_id, filters=filters, limit=limit, offset=offset)
    request = urllib.request.Request(
        f"{elastic_url.rstrip('/')}/{index_name}/_search",
        data=json_data(query).encode("utf-8"),
        method="POST",
        headers=elastic_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    hits = payload.get("hits", {})
    total = hits.get("total", {})
    total_value = total.get("value", 0) if isinstance(total, dict) else int(total or 0)
    rows = tuple(hit.get("_source", {}) for hit in hits.get("hits", ()))
    return rows, int(total_value)


def elastic_headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key = normalize_optional_header(os.environ.get("DOSSIERAGENT_ELASTIC_API_KEY"))
    if api_key is not None:
        headers["Authorization"] = f"ApiKey {api_key}"
    return headers


def authorize_cron_request(request: Request, authorization: str | None) -> str:
    configured_secret = normalize_optional_header(os.environ.get("DOSSIERAGENT_CRON_SECRET"))
    clean_authorization = normalize_optional_header(authorization)
    if configured_secret is not None:
        if clean_authorization == f"Bearer {configured_secret}":
            return "secret"
        raise HTTPException(
            status_code=403,
            detail={
                "code": "cron_secret_required",
                "message": "Secret cron invalide ou manquant.",
                "details": {},
                "retryable": False,
            },
        )

    client_host = request.client.host if request.client is not None else None
    if client_host in LOCAL_CRON_HOSTS:
        return "local"

    raise HTTPException(
        status_code=403,
        detail={
            "code": "local_cron_only",
            "message": "Route cron limitee aux appels locaux quand aucun secret n'est configure.",
            "details": {"client_host": client_host},
            "retryable": False,
        },
    )


def list_all_market_watches(connection: Any) -> tuple[dict[str, Any], ...]:
    rows = connection.execute(
        """
        SELECT * FROM market_watches
        ORDER BY next_run_at IS NULL, next_run_at ASC, created_at ASC
        """
    ).fetchall()
    return tuple({key: row[key] for key in row.keys()} for row in rows)


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

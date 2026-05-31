from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import uuid4

import uvicorn
from dossieragent_agent import ParsedCommand, ai_chat_system_prompt, parse_command
from dossieragent_browser import BrowserJob, run_browser_job
from dossieragent_core.ai import (
    AIMessage as RuntimeAIMessage,
    AIProviderError,
    chat_completion,
    provider_statuses,
)
from dossieragent_core.auth import (
    AuthConfigurationError,
    AuthSession,
    AuthServiceError,
    AuthSignupResult,
    AuthenticatedUser,
    auth_required,
    bearer_token_from_authorization,
    build_auth_client,
    current_auth_user,
    reset_current_auth_user,
    set_current_auth_user,
)
from dossieragent_core.secret_store import (
    AI_PROVIDER_FIELDS,
    redacted_ai_provider_settings,
    set_ai_provider_secrets,
)
from dossieragent_database import build_repositories, create_connection, run_migrations
from dossieragent_processing import (
    analyze_dossier,
    build_contact_packet,
    deduplicate_listing,
    extract_pdf_text,
    normalize_listing,
    rank_listing,
)
from dossieragent_schedule import compute_next_run_at, find_due_watches
from dossieragent_search_engine import (
    build_listing_bulk_ndjson,
    build_listing_search_query,
    parse_bulk_index_response,
)
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool


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
EXTERNAL_AUTH_PASSWORD_HASH_PREFIX = "external-auth"
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
VALID_CONTACT_PACKET_STATUSES = {
    "ready_for_review",
    "approved",
    "rejected",
    "used",
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


class ListingImportUrlRequest(BaseModel):
    url: str = Field(min_length=1)
    watch_id: str | None = None
    source: str = "manual_url"
    criteria: dict[str, Any] = Field(default_factory=dict)
    timeout: float = Field(default=30.0, gt=0)
    html: str | None = None


class BrowserExtractRequest(BaseModel):
    url: str | None = None
    source: str = "manual_url"
    mode: str = "direct_url"
    criteria: dict[str, Any] = Field(default_factory=dict)
    timeout: float = Field(default=30.0, gt=0)
    html: str | None = None


class AgentCommandRequest(BaseModel):
    command: str | None = None
    message: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    execute: bool = True

    def command_text(self) -> str:
        return self.command or self.message or ""


class AIChatMessageRequest(BaseModel):
    role: str
    content: str = Field(min_length=1)


class AIChatRequest(BaseModel):
    provider: str
    model: str
    messages: list[AIChatMessageRequest] = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    use_tools: bool = True


class AIProviderSettingsPatchRequest(BaseModel):
    api_key: str | None = None
    provider_path: str | None = None
    provider_mode: str | None = None
    clear_fields: list[str] = Field(default_factory=list)


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class AuthRegisterRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)
    display_name: str | None = None
    redirect_to: str | None = None


class AuthRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class AuthForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3)
    redirect_to: str | None = None


class ContactPacketCreateRequest(BaseModel):
    listing_id: str
    language: str = "fr"
    tone: str = "polite_direct"
    include_dossier_summary: bool = True


class ContactPacketPatchRequest(BaseModel):
    language: str | None = None
    tone: str | None = None
    status: str | None = None
    message_draft: str | None = None
    questions_to_ask: list[str] | None = None
    dossier_summary: dict[str, Any] | None = None


class ContactPacketMarkUsedRequest(BaseModel):
    channel: str = "manual_copy"


class UserCheckCompleteRequest(BaseModel):
    decision: str
    note: str | None = None


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

    install_auth_middleware(app)
    install_error_handlers(app)
    install_routes(app)
    return app


AUTH_EXEMPT_API_PATHS = {
    "/api/v1",
    "/api/v1/status",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/password/forgot",
    "/api/v1/internal/browser/extract",
    "/api/v1/internal/cron/run-due-watches",
}
AUTH_REQUIRED_API_PATHS = {"/api/v1/me"}


def install_auth_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def auth_context_middleware(request: Request, call_next: Any) -> JSONResponse:
        user_token = set_current_auth_user(None)
        try:
            guard_response = await authenticate_request_if_needed(request)
            if guard_response is not None:
                return guard_response
            return await call_next(request)
        finally:
            reset_current_auth_user(user_token)


async def authenticate_request_if_needed(request: Request) -> JSONResponse | None:
    path = request.url.path
    if not path.startswith("/api/v1/") or path in AUTH_EXEMPT_API_PATHS:
        return None

    authorization = request.headers.get("authorization")
    bearer_token = bearer_token_from_authorization(authorization)
    needs_auth = path in AUTH_REQUIRED_API_PATHS or auth_required()
    if authorization and bearer_token is None:
        return error_response(
            status_code=401,
            code="invalid_authorization_header",
            message="Authorization doit utiliser le format Bearer.",
            retryable=False,
        )
    if bearer_token is None:
        if needs_auth:
            return error_response(
                status_code=401,
                code="authentication_required",
                message="Authentification requise.",
                retryable=False,
            )
        return None

    try:
        auth_user = await run_in_threadpool(build_auth_client().get_user, access_token=bearer_token)
        auth_user = await run_in_threadpool(provision_authenticated_user, auth_user)
    except AuthConfigurationError as exc:
        return error_response(
            status_code=503,
            code="auth_not_configured",
            message=str(exc),
            retryable=False,
        )
    except AuthServiceError as exc:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            retryable=exc.retryable,
        )
    except AuthenticatedUserProvisioningError as exc:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            retryable=False,
        )

    set_current_auth_user(auth_user)
    return None


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

    @app.post("/api/v1/auth/login", tags=["auth"])
    def login(request: AuthLoginRequest) -> dict[str, Any]:
        try:
            session = build_auth_client().login(email=request.email, password=request.password)
            session = provision_auth_session(session)
        except AuthConfigurationError as exc:
            raise auth_not_configured(exc) from exc
        except AuthServiceError as exc:
            raise auth_service_exception(exc) from exc
        except AuthenticatedUserProvisioningError as exc:
            raise auth_provisioning_exception(exc) from exc
        return auth_session_response(session)

    @app.post("/api/v1/auth/register", status_code=201, tags=["auth"])
    def register(request: AuthRegisterRequest) -> dict[str, Any]:
        try:
            result = build_auth_client().register(
                email=request.email,
                password=request.password,
                display_name=clean_form_value(request.display_name),
                redirect_to=clean_form_value(request.redirect_to),
            )
            result = provision_auth_signup_result(result)
        except AuthConfigurationError as exc:
            raise auth_not_configured(exc) from exc
        except AuthServiceError as exc:
            raise auth_service_exception(exc) from exc
        except AuthenticatedUserProvisioningError as exc:
            raise auth_provisioning_exception(exc) from exc
        return auth_signup_result_response(result)

    @app.post("/api/v1/auth/refresh", tags=["auth"])
    def refresh_auth_session(request: AuthRefreshRequest) -> dict[str, Any]:
        try:
            session = build_auth_client().refresh(refresh_token=request.refresh_token)
            session = provision_auth_session(session)
        except AuthConfigurationError as exc:
            raise auth_not_configured(exc) from exc
        except AuthServiceError as exc:
            raise auth_service_exception(exc) from exc
        except AuthenticatedUserProvisioningError as exc:
            raise auth_provisioning_exception(exc) from exc
        return auth_session_response(session)

    @app.post("/api/v1/auth/password/forgot", tags=["auth"])
    def forgot_password(request: AuthForgotPasswordRequest) -> dict[str, Any]:
        try:
            build_auth_client().recover_password(
                email=request.email,
                redirect_to=clean_form_value(request.redirect_to),
            )
        except AuthConfigurationError as exc:
            raise auth_not_configured(exc) from exc
        except AuthServiceError as exc:
            raise auth_service_exception(exc) from exc
        return {"status": "recovery_requested"}

    @app.post("/api/v1/auth/logout", tags=["auth"])
    def logout(authorization: str | None = Header(default=None, alias="Authorization")) -> dict[str, Any]:
        bearer_token = bearer_token_from_authorization(authorization)
        if bearer_token is None:
            return {"status": "logged_out"}
        try:
            build_auth_client().logout(access_token=bearer_token)
        except AuthConfigurationError as exc:
            raise auth_not_configured(exc) from exc
        except AuthServiceError as exc:
            raise auth_service_exception(exc) from exc
        return {"status": "logged_out"}

    @app.get("/api/v1/me", tags=["auth"])
    def me() -> dict[str, Any]:
        auth_user = current_auth_user()
        if auth_user is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "authentication_required",
                    "message": "Authentification requise.",
                    "details": {},
                    "retryable": False,
                },
            )
        return auth_user_response(auth_user)

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

    @app.post("/api/v1/agent/commands", tags=["agent"])
    def handle_agent_command(
        request: AgentCommandRequest,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        parsed = parse_command(request.command_text(), context=request.context)
        if parsed.status == "rejected":
            return agent_command_response(parsed, result=None)
        if not request.execute:
            return agent_command_response(parsed, result=agent_command_plan(parsed))

        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            ensure_user_exists(repositories, user_id)
            result = execute_parsed_agent_command(
                connection,
                repositories,
                user_id=user_id,
                parsed=parsed,
            )
            connection.commit()
            return agent_command_response(parsed, result=result)
        finally:
            connection.close()

    @app.get("/api/v1/ai/providers", tags=["ai"])
    def list_ai_providers() -> dict[str, Any]:
        return {"providers": provider_statuses()}

    @app.get("/api/v1/ai/provider-settings", tags=["ai"])
    def list_ai_provider_settings(request: Request) -> dict[str, Any]:
        authorize_sensitive_settings_request(request)
        return ai_provider_settings_response()

    @app.patch("/api/v1/ai/provider-settings/{provider_id}", tags=["ai"])
    def update_ai_provider_settings(
        provider_id: str,
        settings: AIProviderSettingsPatchRequest,
        request: Request,
    ) -> dict[str, Any]:
        authorize_sensitive_settings_request(request)
        normalized_provider_id = provider_id.strip().lower()
        if normalized_provider_id not in AI_PROVIDER_FIELDS:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "unknown_ai_provider",
                    "message": "Fournisseur IA inconnu.",
                    "details": {"provider": provider_id},
                    "retryable": False,
                },
            )
        values: dict[str, str | None] = {}
        if normalized_provider_id in {"openai", "anthropic", "google"}:
            values["api_key"] = settings.api_key
        if normalized_provider_id == "codex":
            values["provider_path"] = settings.provider_path
            values["provider_mode"] = settings.provider_mode
        set_ai_provider_secrets(
            normalized_provider_id,
            values,
            clear_fields={field.strip() for field in settings.clear_fields if field.strip()},
        )
        return ai_provider_settings_response()

    @app.post("/api/v1/ai/chat", tags=["ai"])
    def handle_ai_chat(
        request: AIChatRequest,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        messages = [RuntimeAIMessage(role=message.role, content=message.content) for message in request.messages]
        latest_user_message = latest_chat_user_message(messages)
        if latest_user_message is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "missing_user_message",
                    "message": "Le chat IA requiert au moins un message utilisateur.",
                    "details": {},
                    "retryable": False,
                },
            )

        if request.use_tools:
            parsed = parse_command(latest_user_message.content, context=request.context)
            if parsed.status == "accepted":
                connection = create_connection()
                try:
                    run_migrations(connection)
                    repositories = build_repositories(connection)
                    ensure_user_exists(repositories, user_id)
                    result = execute_parsed_agent_command(
                        connection,
                        repositories,
                        user_id=user_id,
                        parsed=parsed,
                    )
                    connection.commit()
                    return ai_tool_chat_response(parsed, result=result)
                finally:
                    connection.close()
            if parsed.intent == "blocked_external_contact":
                return ai_tool_chat_response(parsed, result=None)

        try:
            completion = chat_completion(
                request.provider,
                request.model,
                [RuntimeAIMessage(role="system", content=ai_chat_system_prompt()), *messages],
            )
        except AIProviderError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "retryable": exc.retryable,
                },
            ) from exc
        return {
            "id": new_id("chat"),
            **completion,
            "tool_call": None,
        }

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
            run = execute_market_watch_run(
                connection,
                repositories,
                user_id=user_id,
                watch=watch,
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

    @app.post("/api/v1/listings/import-url", status_code=201, tags=["listings"])
    def import_listing_url(
        request: ListingImportUrlRequest,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            ensure_user_exists(repositories, user_id)
            watch = resolve_import_watch(
                repositories,
                user_id=user_id,
                watch_id=request.watch_id,
            )
            criteria = repositories.search_criteria.find(watch["criteria_id"])
            criteria_payload = criteria_response(criteria) if criteria is not None else {}
            extraction = run_browser_extract(
                source=request.source,
                mode="direct_url",
                url=request.url,
                criteria={**criteria_payload, **request.criteria},
                timeout=request.timeout,
                html=request.html,
            )
            if extraction["status"] != "succeeded" or not isinstance(extraction.get("candidate"), dict):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "listing_extraction_failed",
                        "message": "Extraction annonce impossible pour cette URL.",
                        "details": {
                            "status": extraction.get("status"),
                            "error": extraction.get("error"),
                        },
                        "retryable": False,
                    },
                )

            now = utc_now()
            persisted = persist_imported_listing(
                repositories,
                user_id=user_id,
                watch=watch,
                criteria=criteria_payload,
                candidate=extraction["candidate"],
                now=now,
            )
            search_index = index_elastic_listings((persisted["row"],))
            connection.commit()
            return {
                "action": persisted["action"],
                "listing": listing_detail_response(persisted["row"]),
                "dedupe": persisted["dedupe"],
                "browser": {
                    "job_id": extraction["job_id"],
                    "status": extraction["status"],
                    "artifacts": extraction.get("artifacts", []),
                },
                "search_index": search_index,
            }
        finally:
            connection.close()

    @app.post("/api/v1/dossier/documents", status_code=201, tags=["dossier"])
    async def upload_dossier_document(
        file: UploadFile = File(...),
        declared_type: str | None = Form(default=None),
        owner_type: str | None = Form(default="user"),
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        original_filename = file.filename or "document.pdf"
        safe_name = safe_filename(original_filename)
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "empty_upload",
                    "message": "Le fichier envoye est vide.",
                    "details": {"filename": original_filename},
                    "retryable": False,
                },
            )

        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            ensure_user_exists(repositories, user_id)

            document_id = new_id("doc")
            now = utc_now()
            storage_root = resolve_storage_path()
            document_dir = storage_root / "documents" / user_id / document_id
            extracted_dir = storage_root / "extracted_text" / user_id
            document_dir.mkdir(parents=True, exist_ok=True)
            extracted_dir.mkdir(parents=True, exist_ok=True)
            stored_path = document_dir / safe_name
            stored_path.write_bytes(content)

            extraction = extract_pdf_text(stored_path, declared_type=declared_type)
            extracted_text_path: Path | None = None
            if extraction.text:
                extracted_text_path = extracted_dir / f"{document_id}.txt"
                extracted_text_path.write_text(extraction.text, encoding="utf-8")

            issues = list(extraction.issues)
            warnings = list(extraction.warnings)
            if not is_pdf_upload(safe_name, file.content_type):
                issues.append("mime_type_not_pdf")

            status = "needs_review" if issues else "uploaded"
            mime_type = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
            row_data = {
                "id": document_id,
                "user_id": user_id,
                "filename": safe_name,
                "storage_path": str(stored_path),
                "mime_type": mime_type,
                "file_size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "declared_type": clean_form_value(declared_type),
                "detected_type": extraction.detected_type,
                "detected_owner_type": clean_form_value(owner_type) or "user",
                "page_count": extraction.page_count,
                "status": status,
                "extracted_text_path": str(extracted_text_path) if extracted_text_path else None,
                "issues_json": json_data(list(dict.fromkeys(issues))),
                "warnings_json": json_data(list(dict.fromkeys(warnings))),
                "created_at": now,
                "updated_at": now,
            }
            row = repositories.dossier_documents.create(row_data)
            connection.commit()
            return dossier_document_response(row)
        finally:
            connection.close()

    @app.get("/api/v1/dossier/documents", tags=["dossier"])
    def list_dossier_documents(
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            rows = repositories.dossier_documents.list_active_for_user(user_id)
            return {"items": [dossier_document_response(row) for row in rows]}
        finally:
            connection.close()

    @app.get("/api/v1/dossier/documents/{document_id}", tags=["dossier"])
    def get_dossier_document(
        document_id: str,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            row = repositories.dossier_documents.find_for_user(
                user_id=user_id,
                document_id=document_id,
            )
            if row is None:
                raise resource_not_found("document_not_found", "Document introuvable.", "document_id", document_id)
            return dossier_document_response(row)
        finally:
            connection.close()

    @app.get("/api/v1/dossier/documents/{document_id}/preview", tags=["dossier"])
    def preview_dossier_document(
        document_id: str,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> FileResponse:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            row = repositories.dossier_documents.find_for_user(
                user_id=user_id,
                document_id=document_id,
            )
            if row is None or row["status"] == "deleted":
                raise resource_not_found("document_not_found", "Document introuvable.", "document_id", document_id)

            document_path = Path(row["storage_path"])
            if not document_path.exists() or not document_path.is_file():
                raise resource_not_found(
                    "document_file_not_found",
                    "Fichier document introuvable.",
                    "document_id",
                    document_id,
                )

            return FileResponse(
                document_path,
                media_type=row["mime_type"],
                filename=row["filename"],
                content_disposition_type="inline",
            )
        finally:
            connection.close()

    @app.delete("/api/v1/dossier/documents/{document_id}", tags=["dossier"])
    def delete_dossier_document(
        document_id: str,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            row = repositories.dossier_documents.find_for_user(
                user_id=user_id,
                document_id=document_id,
            )
            if row is None or row["status"] == "deleted":
                raise resource_not_found("document_not_found", "Document introuvable.", "document_id", document_id)

            now = utc_now()
            updated = repositories.dossier_documents.update(
                document_id,
                {
                    "status": "deleted",
                    "updated_at": now,
                },
            )
            documents = repositories.dossier_documents.list_active_for_user(user_id, limit=500)
            result = analyze_dossier(documents, now=now)
            create_dossier_snapshot(repositories, user_id=user_id, result=result, now=now)
            connection.commit()
            return dossier_document_response(updated)
        finally:
            connection.close()

    @app.post("/api/v1/dossier/analyze", status_code=201, tags=["dossier"])
    def analyze_dossier_readiness(
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            ensure_user_exists(repositories, user_id)
            documents = repositories.dossier_documents.list_active_for_user(user_id, limit=500)
            now = utc_now()
            result = analyze_dossier(documents, now=now)
            row = create_dossier_snapshot(repositories, user_id=user_id, result=result, now=now)
            connection.commit()
            return dossier_snapshot_response(row)
        finally:
            connection.close()

    @app.get("/api/v1/dossier/readiness", tags=["dossier"])
    def get_dossier_readiness(
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            row = repositories.dossier_snapshots.latest_for_user(user_id)
            if row is None:
                raise resource_not_found("dossier_readiness_not_found", "Analyse dossier introuvable.", "user_id", user_id)
            return dossier_snapshot_response(row)
        finally:
            connection.close()

    @app.post("/api/v1/contact-packets", status_code=201, tags=["contact-packets"])
    def create_contact_packet(
        request: ContactPacketCreateRequest,
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
                    scope="contact_packet_create",
                    idempotency_key=clean_idempotency_key,
                )
                if existing_key is not None:
                    if existing_key["resource_type"] != "contact_packet":
                        raise idempotency_conflict(
                            scope="contact_packet_create",
                            idempotency_key=clean_idempotency_key,
                            expected_resource_type="contact_packet",
                            existing_key=existing_key,
                        )
                    existing_packet = repositories.contact_packets.find_for_user(
                        user_id=user_id,
                        packet_id=existing_key["resource_id"],
                    )
                    if existing_packet is None:
                        raise idempotency_resource_missing(existing_key)
                    existing_check = repositories.user_checks.find_for_resource(
                        user_id=user_id,
                        resource_type="contact_packet",
                        resource_id=existing_packet["id"],
                        check_type="contact_packet_review",
                    )
                    return contact_packet_response(
                        existing_packet,
                        user_check_id=existing_check["id"] if existing_check is not None else None,
                    )

            listing = repositories.listings.find_for_user(user_id=user_id, listing_id=request.listing_id)
            if listing is None:
                raise resource_not_found("listing_not_found", "Annonce introuvable.", "listing_id", request.listing_id)

            snapshot = repositories.dossier_snapshots.latest_for_user(user_id)
            dossier_summary = dossier_summary_for_packet(snapshot) if request.include_dossier_summary else {}
            try:
                draft = build_contact_packet(
                    listing,
                    dossier_summary=dossier_summary,
                    language=request.language,
                    tone=request.tone,
                    include_dossier_summary=request.include_dossier_summary,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "unsupported_contact_packet_option",
                        "message": str(exc),
                        "details": {"language": request.language, "tone": request.tone},
                        "retryable": False,
                    },
                ) from exc

            now = utc_now()
            packet = repositories.contact_packets.create(
                {
                    "id": new_id("pkt"),
                    "user_id": user_id,
                    "listing_id": listing["id"],
                    "language": request.language,
                    "tone": request.tone,
                    "status": "ready_for_review",
                    "message_draft": draft.message_draft,
                    "questions_json": json_data(list(draft.questions_to_ask)),
                    "dossier_summary_json": json_data(dict(draft.dossier_summary)),
                    "used_at": None,
                    "used_channel": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            check = repositories.user_checks.create(
                {
                    "id": new_id("chk"),
                    "user_id": user_id,
                    "type": "contact_packet_review",
                    "resource_type": "contact_packet",
                    "resource_id": packet["id"],
                    "title": "Relire le paquet de contact",
                    "summary": f"Paquet pret pour {listing['title']}. Validation obligatoire avant usage.",
                    "status": "pending",
                    "payload_json": json_data({"packet_id": packet["id"], "listing_id": listing["id"]}),
                    "completed_with": None,
                    "completed_note": None,
                    "created_at": now,
                    "completed_at": None,
                }
            )
            if clean_idempotency_key is not None:
                repositories.idempotency_keys.create(
                    {
                        "id": new_id("idem"),
                        "user_id": user_id,
                        "scope": "contact_packet_create",
                        "idempotency_key": clean_idempotency_key,
                        "resource_type": "contact_packet",
                        "resource_id": packet["id"],
                        "created_at": now,
                    }
                )
            connection.commit()
            return contact_packet_response(packet, user_check_id=check["id"])
        finally:
            connection.close()

    @app.get("/api/v1/contact-packets", tags=["contact-packets"])
    def list_contact_packets(
        limit: int = Query(default=100, ge=1, le=200),
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            rows = repositories.contact_packets.list_by_user(user_id, limit=limit)
            return {"items": [contact_packet_response(row) for row in rows]}
        finally:
            connection.close()

    @app.get("/api/v1/contact-packets/{packet_id}", tags=["contact-packets"])
    def get_contact_packet(
        packet_id: str,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            row = repositories.contact_packets.find_for_user(user_id=user_id, packet_id=packet_id)
            if row is None:
                raise resource_not_found("contact_packet_not_found", "Paquet introuvable.", "packet_id", packet_id)
            return contact_packet_response(row)
        finally:
            connection.close()

    @app.patch("/api/v1/contact-packets/{packet_id}", tags=["contact-packets"])
    def update_contact_packet(
        packet_id: str,
        request: ContactPacketPatchRequest,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            row = repositories.contact_packets.find_for_user(user_id=user_id, packet_id=packet_id)
            if row is None:
                raise resource_not_found("contact_packet_not_found", "Paquet introuvable.", "packet_id", packet_id)

            update_data: dict[str, Any] = {"updated_at": utc_now()}
            if request.language is not None:
                update_data["language"] = request.language
            if request.tone is not None:
                update_data["tone"] = request.tone
            if request.status is not None:
                if request.status not in VALID_CONTACT_PACKET_STATUSES:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": "invalid_contact_packet_status",
                            "message": "Statut de paquet de contact invalide.",
                            "details": {
                                "status": request.status,
                                "allowed": sorted(VALID_CONTACT_PACKET_STATUSES),
                            },
                            "retryable": False,
                        },
                    )
                update_data["status"] = request.status
            if request.message_draft is not None:
                update_data["message_draft"] = request.message_draft
            if request.questions_to_ask is not None:
                update_data["questions_json"] = json_data(request.questions_to_ask)
            if request.dossier_summary is not None:
                update_data["dossier_summary_json"] = json_data(request.dossier_summary)

            updated = repositories.contact_packets.update(packet_id, update_data)
            connection.commit()
            return contact_packet_response(updated)
        finally:
            connection.close()

    @app.post("/api/v1/contact-packets/{packet_id}/mark-used", tags=["contact-packets"])
    def mark_contact_packet_used(
        packet_id: str,
        request: ContactPacketMarkUsedRequest,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            row = repositories.contact_packets.find_for_user(user_id=user_id, packet_id=packet_id)
            if row is None:
                raise resource_not_found("contact_packet_not_found", "Paquet introuvable.", "packet_id", packet_id)

            now = utc_now()
            updated = repositories.contact_packets.update(
                packet_id,
                {
                    "status": "used",
                    "used_at": now,
                    "used_channel": request.channel,
                    "updated_at": now,
                },
            )
            connection.commit()
            return contact_packet_response(updated)
        finally:
            connection.close()

    @app.get("/api/v1/user-checks", tags=["user-checks"])
    def list_user_checks(
        limit: int = Query(default=100, ge=1, le=200),
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            rows = repositories.user_checks.list_pending_for_user(user_id, limit=limit)
            return {"items": [user_check_response(row) for row in rows]}
        finally:
            connection.close()

    @app.post("/api/v1/user-checks/{check_id}/complete", tags=["user-checks"])
    def complete_user_check(
        check_id: str,
        request: UserCheckCompleteRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        if request.decision not in {"approved", "rejected"}:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "invalid_check_decision",
                    "message": "Decision de validation invalide.",
                    "details": {"decision": request.decision, "allowed": ["approved", "rejected"]},
                    "retryable": False,
                },
            )

        user_id = request_user_id(x_demo_user_id)
        clean_idempotency_key = normalize_optional_header(idempotency_key)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)

            if clean_idempotency_key is not None:
                existing_key = repositories.idempotency_keys.find_key(
                    user_id=user_id,
                    scope="user_check_complete",
                    idempotency_key=clean_idempotency_key,
                )
                if existing_key is not None:
                    if (
                        existing_key["resource_type"] != "user_check"
                        or existing_key["resource_id"] != check_id
                    ):
                        raise idempotency_conflict(
                            scope="user_check_complete",
                            idempotency_key=clean_idempotency_key,
                            expected_resource_type="user_check",
                            existing_key=existing_key,
                            requested_resource_id=check_id,
                        )
                    existing_check = repositories.user_checks.find_for_user(
                        user_id=user_id,
                        check_id=existing_key["resource_id"],
                    )
                    if existing_check is None:
                        raise idempotency_resource_missing(existing_key)
                    return user_check_response(existing_check)

            row = repositories.user_checks.find_for_user(user_id=user_id, check_id=check_id)
            if row is None:
                raise resource_not_found("user_check_not_found", "Validation introuvable.", "check_id", check_id)
            if row["status"] != "pending":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "user_check_already_completed",
                        "message": "Validation deja completee.",
                        "details": {"check_id": check_id, "status": row["status"]},
                        "retryable": False,
                    },
                )

            completed = repositories.user_checks.complete(
                check_id=check_id,
                decision=request.decision,
                note=clean_form_value(request.note),
                completed_at=utc_now(),
            )
            if clean_idempotency_key is not None:
                repositories.idempotency_keys.create(
                    {
                        "id": new_id("idem"),
                        "user_id": user_id,
                        "scope": "user_check_complete",
                        "idempotency_key": clean_idempotency_key,
                        "resource_type": "user_check",
                        "resource_id": completed["id"],
                        "created_at": utc_now(),
                    }
                )
            connection.commit()
            return user_check_response(completed)
        finally:
            connection.close()

    @app.get("/api/v1/notifications", tags=["notifications"])
    def list_notifications(
        unread_only: bool = False,
        limit: int = Query(default=100, ge=1, le=200),
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            rows = repositories.notifications.list_for_user(user_id, unread_only=unread_only, limit=limit)
            return {"items": [notification_response(row) for row in rows]}
        finally:
            connection.close()

    @app.post("/api/v1/notifications/{notification_id}/read", tags=["notifications"])
    def mark_notification_read(
        notification_id: str,
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> dict[str, Any]:
        user_id = request_user_id(x_demo_user_id)
        connection = create_connection()
        try:
            run_migrations(connection)
            repositories = build_repositories(connection)
            row = repositories.notifications.find_for_user(user_id=user_id, notification_id=notification_id)
            if row is None:
                raise resource_not_found(
                    "notification_not_found",
                    "Notification introuvable.",
                    "notification_id",
                    notification_id,
                )
            updated = repositories.notifications.mark_read(notification_id=notification_id, read_at=utc_now())
            connection.commit()
            return notification_response(updated)
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

                run = execute_market_watch_run(
                    connection,
                    repositories,
                    user_id=watch["user_id"],
                    watch=watch,
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

    @app.post("/api/v1/internal/browser/extract", tags=["internal"])
    def extract_listing_with_browser(
        request: Request,
        extract_request: BrowserExtractRequest,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any]:
        guard = authorize_internal_browser_request(request, authorization)
        criteria = dict(extract_request.criteria)
        if extract_request.url is not None:
            criteria["url"] = extract_request.url
        result = run_browser_extract(
            source=extract_request.source,
            mode=extract_request.mode,
            url=extract_request.url,
            criteria=criteria,
            timeout=extract_request.timeout,
            html=extract_request.html,
        )
        return {
            "guard": guard,
            **result,
        }


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
    async def not_found_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return await http_exception_handler(request, exc)
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
            "missing_docs": missing_document_types(json_field(dossier_snapshot["missing_documents_json"], [])),
            "valid_docs": json_field(dossier_snapshot["valid_documents_json"], []),
            "warnings": json_field(dossier_snapshot.get("warnings_json"), []),
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
                "source_url": listing.get("source_url"),
                "canonical_url": listing.get("canonical_url"),
                "image_urls": listing_image_urls(listing),
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


def agent_command_response(parsed: ParsedCommand, *, result: dict[str, Any] | None) -> dict[str, Any]:
    payload = {
        "status": parsed.status,
        "intent": parsed.intent,
        "action": parsed.action,
        "summary": parsed.summary,
        "parameters": dict(parsed.parameters),
        "guardrails": list(parsed.guardrails),
        "result": result,
    }
    return payload


def agent_command_plan(parsed: ParsedCommand) -> dict[str, Any]:
    return {
        "type": "command_plan",
        "requires_confirmation": True,
        "intent": parsed.intent,
        "action": parsed.action,
        "parameters": dict(parsed.parameters),
        "guardrails": list(parsed.guardrails),
    }


def latest_chat_user_message(messages: list[RuntimeAIMessage]) -> RuntimeAIMessage | None:
    for message in reversed(messages):
        if message.role == "user":
            return message
    return None


def ai_provider_settings_response() -> dict[str, Any]:
    redacted_settings = redacted_ai_provider_settings()
    status_by_id = {provider["id"]: provider for provider in provider_statuses()}
    return {
        "providers": [
            {
                **provider,
                "status": status_by_id.get(provider["id"], {}),
            }
            for provider in redacted_settings["providers"]
        ]
    }


def authorize_sensitive_settings_request(request: Request) -> None:
    if current_auth_user() is not None:
        return
    if auth_required():
        raise HTTPException(
            status_code=401,
            detail={
                "code": "authentication_required",
                "message": "Authentification requise.",
                "details": {},
                "retryable": False,
            },
        )
    client_host = request.client.host if request.client is not None else ""
    if client_host in LOCAL_CRON_HOSTS:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "code": "local_settings_only",
            "message": "Configuration locale limitee aux appels locaux sans authentification.",
            "details": {"client_host": client_host},
            "retryable": False,
        },
    )


def ai_tool_chat_response(parsed: ParsedCommand, *, result: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": new_id("chat"),
        "provider": "dossieragent_tools",
        "model": "supervised-command-router",
        "message": {
            "role": "assistant",
            "content": ai_tool_message_content(parsed, result=result),
        },
        "tool_call": {
            "status": parsed.status,
            "intent": parsed.intent,
            "action": parsed.action,
            "summary": parsed.summary,
            "parameters": dict(parsed.parameters),
            "guardrails": list(parsed.guardrails),
            "result": result,
        },
        "usage": None,
    }


def ai_tool_message_content(parsed: ParsedCommand, *, result: dict[str, Any] | None) -> str:
    if parsed.status == "rejected":
        return parsed.summary
    if result is None:
        return parsed.summary
    result_type = result.get("type")
    if result_type == "listing_collection":
        count = len(result.get("items", []))
        return f"{parsed.summary} {count} annonces trouvees dans la base locale."
    if result_type == "agent_run":
        run = result.get("run", {})
        return f"{parsed.summary} Run {run.get('id', '-')} cree en mode supervise."
    if result_type == "dossier_snapshot":
        snapshot = result.get("snapshot", {})
        return f"{parsed.summary} Score dossier: {snapshot.get('readiness_score', '-')}%."
    if result_type == "market_watch":
        watch = result.get("watch", {})
        return f"{parsed.summary} Veille {watch.get('id', '-')} prete."
    return parsed.summary


def execute_parsed_agent_command(
    connection: Any,
    repositories: Any,
    *,
    user_id: str,
    parsed: ParsedCommand,
) -> dict[str, Any]:
    if parsed.intent == "run_market_watch":
        watch_id = parsed.parameters.get("watch_id")
        return execute_command_run_market_watch(
            connection,
            repositories,
            user_id=user_id,
            watch_id=str(watch_id) if watch_id else None,
        )
    if parsed.intent == "analyze_dossier":
        documents = repositories.dossier_documents.list_active_for_user(user_id, limit=500)
        now = utc_now()
        result = analyze_dossier(documents, now=now)
        snapshot = create_dossier_snapshot(repositories, user_id=user_id, result=result, now=now)
        return {
            "type": "dossier_snapshot",
            "snapshot": dossier_snapshot_response(snapshot),
        }
    if parsed.intent == "show_recommended_listings":
        listings = repositories.dashboard.recommended_listings(user_id, limit=5)
        return {
            "type": "listing_collection",
            "items": [listing_summary_response(row) for row in listings],
        }
    if parsed.intent == "create_market_watch":
        return execute_command_create_market_watch(repositories, user_id=user_id, parsed=parsed)
    return {
        "type": "noop",
        "message": "Intent accepte mais non execute.",
    }


def execute_command_run_market_watch(
    connection: Any,
    repositories: Any,
    *,
    user_id: str,
    watch_id: str | None,
) -> dict[str, Any]:
    watch = resolve_import_watch(repositories, user_id=user_id, watch_id=watch_id)
    active_run = repositories.agent_runs.active_for_watch(user_id=user_id, watch_id=watch["id"])
    if active_run is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "run_already_active",
                "message": "Un run est deja actif pour cette veille.",
                "details": {"watch_id": watch["id"], "run_id": active_run["id"]},
                "retryable": True,
            },
        )

    now = utc_now()
    run = execute_market_watch_run(
        connection,
        repositories,
        user_id=user_id,
        watch=watch,
        trigger_type="command",
        now=now,
    )
    repositories.market_watches.update(
        watch["id"],
        {
            "last_run_at": now,
            "updated_at": now,
        },
    )
    return {
        "type": "agent_run",
        "run": agent_run_response(run),
    }


def execute_command_create_market_watch(
    repositories: Any,
    *,
    user_id: str,
    parsed: ParsedCommand,
) -> dict[str, Any]:
    city = str(parsed.parameters["city"])
    budget_max = parsed.parameters.get("budget_max")
    rooms_min = parsed.parameters.get("rooms_min")
    frequency = str(parsed.parameters.get("frequency") or "daily")
    now = utc_now()
    criteria = repositories.search_criteria.create(
        {
            "id": new_id("crit"),
            "user_id": user_id,
            "mode": "rent",
            "cities_json": json_data([city]),
            "districts_json": json_data([]),
            "budget_min": None,
            "budget_max": budget_max,
            "surface_min": None,
            "rooms_min": rooms_min,
            "languages_json": json_data(["fr"]),
            "filters_json": json_data({}),
            "created_at": now,
            "updated_at": now,
        }
    )
    watch = repositories.market_watches.create(
        {
            "id": new_id("watch"),
            "user_id": user_id,
            "criteria_id": criteria["id"],
            "name": f"{city} location",
            "status": "active",
            "frequency": frequency,
            "next_run_at": compute_next_run_at(frequency, from_time=now),
            "last_run_at": None,
            "source_config_json": json_data({"sources": ["manual_urls"]}),
            "created_at": now,
            "updated_at": now,
        }
    )
    return {
        "type": "market_watch",
        "criteria": criteria_response(criteria),
        "watch": market_watch_response(watch),
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
        "source_url": row.get("source_url"),
        "canonical_url": row.get("canonical_url"),
        "image_urls": listing_image_urls(row),
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


def listing_image_urls(row: dict[str, Any]) -> list[str]:
    raw_payload = json_field(row.get("raw_payload_json"), row.get("raw_payload", {}))
    base_url = first_string(row.get("canonical_url"), row.get("source_url")) or ""
    return sanitize_image_urls(extract_image_url_candidates(raw_payload), base_url=base_url)


def extract_image_url_candidates(value: Any) -> list[Any]:
    candidates: list[Any] = []
    if value is None:
        return candidates
    if isinstance(value, str):
        candidates.append(value)
        return candidates
    if isinstance(value, list | tuple):
        for item in value:
            candidates.extend(extract_image_url_candidates(item))
        return candidates
    if not isinstance(value, dict):
        return candidates

    for key in ("image_urls", "images", "photos", "image", "photo", "thumbnail_url", "thumbnailUrl"):
        if key in value:
            candidates.extend(extract_image_url_candidates(value[key]))

    for key in ("candidate", "raw_payload"):
        nested = value.get(key)
        if isinstance(nested, dict):
            candidates.extend(extract_image_url_candidates(nested))
    return candidates


def sanitize_image_urls(values: list[Any], *, base_url: str, limit: int = 8) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned or len(cleaned) > 2048:
            continue
        image_url = sanitize_http_url(cleaned, base_url=base_url)
        if image_url is None or image_url in seen:
            continue
        seen.add(image_url)
        urls.append(image_url)
        if len(urls) >= limit:
            break
    return urls


def sanitize_http_url(value: str, *, base_url: str) -> str | None:
    joined = urljoin(base_url, value)
    parsed = urlsplit(joined)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


def first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def dossier_document_response(row: dict[str, Any]) -> dict[str, Any]:
    has_extracted_text = bool(row.get("extracted_text_path"))
    return {
        "id": row["id"],
        "document_id": row["id"],
        "status": row["status"],
        "filename": row["filename"],
        "mime_type": row["mime_type"],
        "file_size": row["file_size"],
        "sha256": row["sha256"],
        "declared_type": row.get("declared_type"),
        "detected_type": row.get("detected_type"),
        "detected_owner_type": row.get("detected_owner_type"),
        "page_count": row.get("page_count"),
        "has_extracted_text": has_extracted_text,
        "analysis_status": "queued" if row["status"] == "uploaded" else row["status"],
        "issues": json_field(row.get("issues_json"), []),
        "warnings": json_field(row.get("warnings_json"), []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_dossier_snapshot(
    repositories: Any,
    *,
    user_id: str,
    result: Any,
    now: str,
) -> dict[str, Any]:
    return repositories.dossier_snapshots.create(
        {
            "id": new_id("snap"),
            "user_id": user_id,
            "readiness_score": result.readiness_score,
            "can_contact": int(result.can_contact),
            "can_send_full_dossier": int(result.can_send_full_dossier),
            "missing_documents_json": json_data([item.as_dict() for item in result.missing_documents]),
            "valid_documents_json": json_data(list(result.valid_documents)),
            "warnings_json": json_data(list(result.warnings)),
            "recommendations_json": json_data(list(result.recommendations)),
            "created_at": now,
        }
    )


def dossier_snapshot_response(row: dict[str, Any]) -> dict[str, Any]:
    missing_documents = json_field(row.get("missing_documents_json"), [])
    valid_documents = json_field(row.get("valid_documents_json"), [])
    warnings = json_field(row.get("warnings_json"), [])
    recommendations = json_field(row.get("recommendations_json"), [])
    missing_types = missing_document_types(missing_documents)
    return {
        "id": row["id"],
        "snapshot_id": row["id"],
        "readiness_score": row["readiness_score"],
        "can_contact": bool(row["can_contact"]),
        "can_send_full_dossier": bool(row["can_send_full_dossier"]),
        "missing_documents": missing_documents,
        "missing_docs": missing_types,
        "valid_documents": valid_documents,
        "valid_docs": valid_documents,
        "warnings": warnings,
        "recommendations": recommendations,
        "created_at": row["created_at"],
    }


def dossier_summary_for_packet(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "can_contact": False,
            "can_send_full_dossier": False,
            "missing_documents": [],
            "readiness_score": None,
        }
    return {
        "can_contact": bool(row["can_contact"]),
        "can_send_full_dossier": bool(row["can_send_full_dossier"]),
        "missing_documents": missing_document_types(json_field(row.get("missing_documents_json"), [])),
        "readiness_score": row["readiness_score"],
    }


def missing_document_types(value: Any) -> list[str]:
    documents = value if isinstance(value, list) else []
    types: list[str] = []
    for document in documents:
        if isinstance(document, dict) and document.get("type") is not None:
            types.append(str(document["type"]))
        elif isinstance(document, str):
            types.append(document)
    return types


def run_browser_extract(
    *,
    source: str,
    mode: str,
    url: str | None,
    criteria: dict[str, Any],
    timeout: float,
    html: str | None,
) -> dict[str, Any]:
    job_criteria = dict(criteria)
    if url is not None:
        job_criteria["url"] = url
    try:
        job = BrowserJob.from_mapping(
            {
                "source": source,
                "mode": mode,
                "criteria": job_criteria,
                "timeout": timeout,
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_browser_job",
                "message": "Parametres d'extraction navigateur invalides.",
                "details": {"error": str(exc)},
                "retryable": False,
            },
        ) from exc

    result = run_browser_job(job, html=html)
    if hasattr(result, "as_dict"):
        payload = result.as_dict()
    elif isinstance(result, dict):
        payload = dict(result)
    else:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "browser_invalid_result",
                "message": "Le worker navigateur a retourne un resultat invalide.",
                "details": {"type": type(result).__name__},
                "retryable": False,
            },
    )
    return payload


class WatchRunPipelineError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable


def execute_market_watch_run(
    connection: Any,
    repositories: Any,
    *,
    user_id: str,
    watch: dict[str, Any],
    trigger_type: str,
    now: str,
) -> dict[str, Any]:
    del connection
    run = create_agent_run(
        repositories,
        user_id=user_id,
        watch_id=watch["id"],
        trigger_type=trigger_type,
        now=now,
    )
    summary = empty_run_summary()

    try:
        criteria_row = repositories.search_criteria.find(watch["criteria_id"])
        if criteria_row is None:
            raise WatchRunPipelineError(
                "search_criteria_not_found",
                "Les criteres de la veille sont introuvables.",
                details={"criteria_id": watch["criteria_id"], "watch_id": watch["id"]},
            )

        criteria = criteria_response(criteria_row)
        dossier_context = dossier_summary_for_packet(repositories.dossier_snapshots.latest_for_user(user_id))
        source_config = json_field(watch.get("source_config_json"), {})
        source_entries = watch_source_entries(source_config)
        if not source_entries:
            raise WatchRunPipelineError(
                "watch_sources_missing",
                "La veille ne contient aucune source executable.",
                details={"watch_id": watch["id"], "source_config": source_config},
            )

        update_agent_run_step(repositories, run, "source_scan", now)
        create_agent_event(
            repositories,
            run_id=run["id"],
            user_id=user_id,
            event_type="source_scan_started",
            severity="info",
            message="Scan des sources demarre.",
            payload={"source_count": len(source_entries), "watch_id": watch["id"]},
            now=now,
        )
        candidates = extract_watch_candidates(source_entries, criteria=criteria, now=now)
        summary["candidate_count"] = len(candidates)
        summary["scanned_candidates"] = len(candidates)
        create_agent_event(
            repositories,
            run_id=run["id"],
            user_id=user_id,
            event_type="source_scan_finished",
            severity="info",
            message="Scan des sources termine.",
            payload={"candidate_count": len(candidates), "source_count": len(source_entries)},
            now=now,
        )

        update_agent_run_step(repositories, run, "normalized", now)
        create_agent_event(
            repositories,
            run_id=run["id"],
            user_id=user_id,
            event_type="normalized",
            severity="info",
            message="Candidats normalises.",
            payload={"candidate_count": len(candidates)},
            now=now,
        )

        changed_rows: list[dict[str, Any]] = []
        for candidate in candidates:
            persisted = persist_imported_listing(
                repositories,
                user_id=user_id,
                watch=watch,
                criteria=criteria,
                candidate=candidate,
                now=now,
                dossier_context=dossier_context,
            )
            changed_rows.append(persisted["row"])
            accumulate_run_summary(summary, persisted)

        update_agent_run_step(repositories, run, "deduped", now)
        create_agent_event(
            repositories,
            run_id=run["id"],
            user_id=user_id,
            event_type="deduped",
            severity="info",
            message="Doublons et reposts evalues.",
            payload={
                "new_count": summary["new_count"],
                "duplicate_count": summary["duplicate_count"],
                "repost_count": summary["repost_count"],
            },
            now=now,
        )

        update_agent_run_step(repositories, run, "ranked", now)
        create_agent_event(
            repositories,
            run_id=run["id"],
            user_id=user_id,
            event_type="ranked",
            severity="info",
            message="Annonces classees selon les criteres et le dossier.",
            payload={"recommended_count": summary["recommended_count"]},
            now=now,
        )

        update_agent_run_step(repositories, run, "indexed", now)
        search_index = index_elastic_listings(tuple(changed_rows))
        summary["search_index"] = search_index
        summary["indexed_count"] = int(search_index.get("indexed") or 0)
        create_agent_event(
            repositories,
            run_id=run["id"],
            user_id=user_id,
            event_type="indexed" if search_index.get("status") == "indexed" else "index_skipped",
            severity="info" if search_index.get("status") == "indexed" else "warning",
            message="Indexation recherche terminee."
            if search_index.get("status") == "indexed"
            else "Indexation recherche ignoree ou indisponible.",
            payload=search_index,
            now=now,
        )

        update_agent_run_step(repositories, run, "notifications", now)
        notification_count = create_watch_run_notification(
            repositories,
            user_id=user_id,
            run_id=run["id"],
            summary=summary,
            now=now,
        )
        summary["notifications_created"] = notification_count
        create_agent_event(
            repositories,
            run_id=run["id"],
            user_id=user_id,
            event_type="notifications_created",
            severity="info",
            message="Notifications de veille creees.",
            payload={"count": notification_count},
            now=now,
        )

        finalize_run_summary(summary)
        run = repositories.agent_runs.update(
            run["id"],
            {
                "status": "completed",
                "current_step": "completed",
                "summary_json": json_data(summary),
                "error_json": None,
                "updated_at": now,
                "completed_at": now,
            },
        )
        create_agent_event(
            repositories,
            run_id=run["id"],
            user_id=user_id,
            event_type="completed",
            severity="info",
            message="Run de veille termine.",
            payload={"status": "completed", "summary": summary},
            now=now,
        )
        return run
    except Exception as exc:
        error_payload = watch_run_error_payload(exc)
        summary["errors"] = [*summary.get("errors", []), error_payload]
        finalize_run_summary(summary)
        create_agent_event(
            repositories,
            run_id=run["id"],
            user_id=user_id,
            event_type="failed",
            severity="error",
            message=error_payload["message"],
            payload=error_payload,
            now=now,
        )
        return repositories.agent_runs.update(
            run["id"],
            {
                "status": "failed",
                "current_step": "failed",
                "summary_json": json_data(summary),
                "error_json": json_data(error_payload),
                "updated_at": now,
                "completed_at": now,
            },
        )


def watch_source_entries(source_config: Any) -> list[dict[str, Any]]:
    if not isinstance(source_config, dict):
        return []

    raw_sources = source_config.get("sources") or []
    if isinstance(raw_sources, dict) or isinstance(raw_sources, str):
        raw_sources = [raw_sources]
    if not isinstance(raw_sources, list | tuple):
        return []

    entries: list[dict[str, Any]] = []
    for raw_source in raw_sources:
        if isinstance(raw_source, dict):
            entries.extend(watch_source_entries_from_mapping(raw_source, source_config))
        elif isinstance(raw_source, str):
            entries.extend(watch_source_entries_from_legacy_name(raw_source, source_config))
    return entries


def watch_source_entries_from_mapping(
    raw_source: dict[str, Any],
    source_config: dict[str, Any],
) -> list[dict[str, Any]]:
    source = first_string(raw_source.get("source"), source_config.get("source")) or "demo_seed"
    mode = first_string(raw_source.get("mode")) or "list_page"
    timeout = positive_float(raw_source.get("timeout") or source_config.get("timeout"), default=30.0)
    base_entry = {
        "source": source,
        "mode": mode,
        "timeout": timeout,
        "html": raw_source.get("html"),
        "detail_html_by_url": raw_source.get("detail_html_by_url") or raw_source.get("details") or {},
    }

    url = first_string(raw_source.get("url"), raw_source.get("list_url"), raw_source.get("search_url"))
    urls = raw_source.get("urls")
    if mode == "direct_url" and url is None and isinstance(urls, list | tuple):
        return [
            {**base_entry, "url": str(candidate_url).strip()}
            for candidate_url in urls
            if str(candidate_url).strip()
        ]
    if url is None:
        return []
    return [{**base_entry, "url": url}]


def watch_source_entries_from_legacy_name(
    source_name: str,
    source_config: dict[str, Any],
) -> list[dict[str, Any]]:
    urls = source_config.get(source_name) or source_config.get("urls")
    if not isinstance(urls, list | tuple):
        return []
    source = "manual_url" if source_name == "manual_urls" else "demo_seed"
    timeout = positive_float(source_config.get("timeout"), default=30.0)
    return [
        {
            "source": source,
            "mode": "direct_url",
            "timeout": timeout,
            "url": str(url).strip(),
            "html": None,
            "detail_html_by_url": {},
        }
        for url in urls
        if str(url).strip()
    ]


def extract_watch_candidates(
    source_entries: list[dict[str, Any]],
    *,
    criteria: dict[str, Any],
    now: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entry in source_entries:
        mode = entry["mode"]
        if mode == "list_page":
            candidates.extend(extract_watch_list_page_candidates(entry, criteria=criteria, now=now))
        elif mode == "direct_url":
            candidates.append(extract_watch_detail_candidate(entry, criteria=criteria, now=now))
        else:
            raise WatchRunPipelineError(
                "unsupported_watch_source_mode",
                "Mode de source non supporte pour la veille.",
                details={"mode": mode, "url": entry.get("url"), "source": entry.get("source")},
            )
    return candidates


def extract_watch_list_page_candidates(
    entry: dict[str, Any],
    *,
    criteria: dict[str, Any],
    now: str,
) -> list[dict[str, Any]]:
    result = run_browser_extract(
        source=str(entry["source"]),
        mode="list_page",
        url=str(entry["url"]),
        criteria=criteria,
        timeout=float(entry["timeout"]),
        html=entry.get("html") if isinstance(entry.get("html"), str) else None,
    )
    ensure_browser_extraction_succeeded(result, stage="extract_listing_urls", entry=entry)
    candidate = result.get("candidate")
    items = candidate.get("items") if isinstance(candidate, dict) else None
    if not isinstance(items, list):
        raise WatchRunPipelineError(
            "listing_url_extraction_invalid",
            "Le worker navigateur n'a pas retourne de liste d'URL exploitable.",
            details={"source": entry.get("source"), "url": entry.get("url")},
        )

    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        listing_url = first_string(item.get("listing_url"), item.get("url"))
        if listing_url is None:
            raise WatchRunPipelineError(
                "listing_url_missing",
                "Un candidat de page liste ne contient pas d'URL annonce.",
                details={"source": entry.get("source"), "url": entry.get("url")},
            )
        detail_entry = {
            **entry,
            "mode": "direct_url",
            "url": listing_url,
            "html": detail_html_for_url(entry, listing_url),
            "list_item": item,
        }
        candidates.append(extract_watch_detail_candidate(detail_entry, criteria=criteria, now=now))
    return candidates


def extract_watch_detail_candidate(
    entry: dict[str, Any],
    *,
    criteria: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    detail_criteria = criteria_for_listing_detail(criteria, entry.get("list_item"))
    result = run_browser_extract(
        source=str(entry["source"]),
        mode="direct_url",
        url=str(entry["url"]),
        criteria=detail_criteria,
        timeout=float(entry["timeout"]),
        html=entry.get("html") if isinstance(entry.get("html"), str) else None,
    )
    ensure_browser_extraction_succeeded(result, stage="extract_listing_details", entry=entry)
    candidate = result.get("candidate")
    if not isinstance(candidate, dict):
        raise WatchRunPipelineError(
            "listing_detail_extraction_invalid",
            "Le worker navigateur n'a pas retourne d'annonce exploitable.",
            details={"source": entry.get("source"), "url": entry.get("url")},
        )
    return enrich_watch_candidate(candidate, entry=entry, now=now)


def ensure_browser_extraction_succeeded(
    result: dict[str, Any],
    *,
    stage: str,
    entry: dict[str, Any],
) -> None:
    if result.get("status") == "succeeded":
        return
    raise WatchRunPipelineError(
        "browser_extraction_failed",
        "Extraction navigateur echouee.",
        details={
            "stage": stage,
            "source": entry.get("source"),
            "mode": entry.get("mode"),
            "url": entry.get("url"),
            "status": result.get("status"),
            "error": result.get("error"),
        },
        retryable=True,
    )


def criteria_for_listing_detail(criteria: dict[str, Any], list_item: Any) -> dict[str, Any]:
    detail_criteria = dict(criteria)
    if isinstance(list_item, dict):
        detail_criteria["city"] = first_string(list_item.get("city")) or first_sequence_item(criteria.get("cities"))
        detail_criteria["district"] = first_string(list_item.get("district")) or first_sequence_item(
            criteria.get("districts")
        )
        return detail_criteria
    detail_criteria["city"] = first_sequence_item(criteria.get("cities"))
    detail_criteria["district"] = first_sequence_item(criteria.get("districts"))
    return detail_criteria


def enrich_watch_candidate(candidate: dict[str, Any], *, entry: dict[str, Any], now: str) -> dict[str, Any]:
    payload = dict(candidate)
    raw_payload = dict(payload.get("raw_payload") or {})
    raw_payload["watch_run"] = {
        "source": entry.get("source"),
        "list_url": entry.get("list_item", {}).get("source_url") if isinstance(entry.get("list_item"), dict) else None,
        "listing_url": entry.get("url"),
        "imported_by": "api.market_watch.run",
    }
    if isinstance(entry.get("list_item"), dict):
        raw_payload["list_item"] = dict(entry["list_item"])
    payload["raw_payload"] = raw_payload
    payload.setdefault("first_seen_at", now)
    payload.setdefault("last_seen_at", now)
    return payload


def detail_html_for_url(entry: dict[str, Any], listing_url: str) -> str | None:
    details = entry.get("detail_html_by_url")
    if not isinstance(details, dict):
        return None
    html = details.get(listing_url) or details.get(strip_url_query(listing_url))
    return html if isinstance(html, str) else None


def strip_url_query(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def accumulate_run_summary(summary: dict[str, Any], persisted: dict[str, Any]) -> None:
    row = persisted["row"]
    dedupe = persisted["dedupe"]
    dedupe_status = dedupe.get("status")
    if dedupe_status == "duplicate":
        summary["duplicate_count"] += 1
        summary["duplicates"] += 1
    elif dedupe_status == "repost":
        summary["repost_count"] += 1
        summary["reposts"] += 1
    else:
        summary["new_count"] += 1
        summary["new_listings"] += 1

    if row.get("status") == "recommended" or float(row.get("fit_score") or 0) >= 80:
        summary["recommended_count"] += 1
        summary["strong_matches"] += 1


def finalize_run_summary(summary: dict[str, Any]) -> None:
    summary["scanned_candidates"] = int(summary.get("candidate_count") or 0)
    summary["new_listings"] = int(summary.get("new_count") or 0)
    summary["duplicates"] = int(summary.get("duplicate_count") or 0)
    summary["reposts"] = int(summary.get("repost_count") or 0)
    summary["strong_matches"] = int(summary.get("recommended_count") or 0)
    summary.setdefault("search_index", {"status": "not_attempted", "attempted": 0, "indexed": 0, "errors": []})
    summary.setdefault("notifications_created", 0)


def create_watch_run_notification(
    repositories: Any,
    *,
    user_id: str,
    run_id: str,
    summary: dict[str, Any],
    now: str,
) -> int:
    repositories.notifications.create(
        {
            "id": new_id("ntf"),
            "user_id": user_id,
            "type": "watch_run_completed",
            "title": "Veille executee",
            "body": (
                f"{summary['candidate_count']} candidats, "
                f"{summary['new_count']} nouvelles annonces, "
                f"{summary['recommended_count']} recommandations."
            ),
            "resource_type": "agent_run",
            "resource_id": run_id,
            "read_at": None,
            "created_at": now,
        }
    )
    return 1


def update_agent_run_step(
    repositories: Any,
    run: dict[str, Any],
    step: str,
    now: str,
) -> dict[str, Any]:
    return repositories.agent_runs.update(run["id"], {"current_step": step, "updated_at": now})


def create_agent_event(
    repositories: Any,
    *,
    run_id: str,
    user_id: str,
    event_type: str,
    severity: str,
    message: str,
    payload: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    return repositories.agent_events.create(
        {
            "id": new_id("evt"),
            "run_id": run_id,
            "user_id": user_id,
            "type": event_type,
            "severity": severity,
            "message": message,
            "payload_json": json_data(payload),
            "created_at": now,
        }
    )


def watch_run_error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, WatchRunPipelineError):
        return {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "retryable": exc.retryable,
        }
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return {
            "code": str(detail.get("code") or "http_error"),
            "message": str(detail.get("message") or exc.detail or "Erreur HTTP pendant le run."),
            "details": detail.get("details") if isinstance(detail.get("details"), dict) else {},
            "retryable": bool(detail.get("retryable", False)),
        }
    return {
        "code": "watch_run_failed",
        "message": str(exc) or "Run de veille echoue.",
        "details": {"type": type(exc).__name__},
        "retryable": False,
    }


def first_sequence_item(value: Any) -> str | None:
    if isinstance(value, list | tuple) and value:
        item = value[0]
        return str(item).strip() if item is not None and str(item).strip() else None
    return None


def positive_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def resolve_import_watch(
    repositories: Any,
    *,
    user_id: str,
    watch_id: str | None,
) -> dict[str, Any]:
    if watch_id is not None:
        watch = repositories.market_watches.find(watch_id)
        if watch is None or watch["user_id"] != user_id:
            raise resource_not_found("market_watch_not_found", "Veille introuvable.", "watch_id", watch_id)
        return watch

    watches = repositories.market_watches.list_by_user(user_id, limit=100, order_by="updated_at")
    for watch in watches:
        if watch["status"] == "active":
            return watch
    if watches:
        return watches[0]
    raise HTTPException(
        status_code=422,
        detail={
            "code": "market_watch_required",
            "message": "Une veille est requise pour importer une annonce.",
            "details": {},
            "retryable": False,
        },
    )


def persist_imported_listing(
    repositories: Any,
    *,
    user_id: str,
    watch: dict[str, Any],
    criteria: dict[str, Any],
    candidate: dict[str, Any],
    now: str,
    dossier_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_listing(candidate)
    ranking = rank_listing(normalized, criteria, dossier_context=dossier_context, now=now)
    existing_listings = repositories.listings.list_by_user(user_id, limit=1000)
    dedupe = deduplicate_listing(normalized, existing_listings)
    existing = repositories.listings.find_by_canonical_hash_for_user(
        user_id=user_id,
        canonical_url_hash=normalized.canonical_url_hash,
    )
    if existing is None and dedupe.status == "duplicate" and dedupe.matched_listing_id is not None:
        existing = repositories.listings.find_for_user(
            user_id=user_id,
            listing_id=dedupe.matched_listing_id,
        )

    if existing is not None:
        update_data = imported_listing_update_data(
            normalized=normalized,
            candidate=candidate,
            ranking=ranking,
            dedupe=dedupe,
            now=now,
            preserve_status=existing["status"],
        )
        if dedupe.matched_listing_id == existing["id"]:
            update_data["duplicate_of_listing_id"] = existing.get("duplicate_of_listing_id")
        row = repositories.listings.update(
            existing["id"],
            update_data,
        )
        return {
            "action": "updated",
            "row": row,
            "dedupe": dedupe_response(dedupe),
        }

    row = repositories.listings.create(
        {
            "id": new_id("lst"),
            "user_id": user_id,
            "watch_id": watch["id"],
            **imported_listing_base_data(
                normalized=normalized,
                candidate=candidate,
                ranking=ranking,
                dedupe=dedupe,
                now=now,
            ),
        }
    )
    return {
        "action": "created",
        "row": row,
        "dedupe": dedupe_response(dedupe),
    }


def imported_listing_base_data(
    *,
    normalized: Any,
    candidate: dict[str, Any],
    ranking: Any,
    dedupe: Any,
    now: str,
) -> dict[str, Any]:
    status = status_for_imported_listing(ranking.fit_score, dedupe.status)
    return {
        "source": normalized.source,
        "source_url": normalized.source_url,
        "canonical_url": normalized.canonical_url,
        "canonical_url_hash": normalized.canonical_url_hash,
        "source_listing_id": normalized.source_listing_id,
        "title": normalized.title,
        "description": normalized.description,
        "city": normalized.city,
        "district": normalized.district,
        "postal_code": normalized.postal_code,
        "price": normalized.price,
        "currency": normalized.currency,
        "surface": normalized.surface,
        "rooms": normalized.rooms,
        "agency_name": normalized.agency_name,
        "contact_hint": candidate.get("contact_hint"),
        "composite_fingerprint": normalized.composite_fingerprint,
        "duplicate_of_listing_id": dedupe.matched_listing_id,
        "status": status,
        "fit_score": ranking.fit_score,
        "fit_level": ranking.fit_level,
        "risk_flags_json": json_data(list(ranking.risk_flags)),
        "explanation_json": json_data(list(ranking.reasons)),
        "raw_payload_json": json_data(imported_listing_raw_payload(candidate, dedupe, ranking)),
        "first_seen_at": now,
        "last_seen_at": now,
        "created_at": now,
        "updated_at": now,
    }


def imported_listing_update_data(
    *,
    normalized: Any,
    candidate: dict[str, Any],
    ranking: Any,
    dedupe: Any,
    now: str,
    preserve_status: str,
) -> dict[str, Any]:
    data = imported_listing_base_data(
        normalized=normalized,
        candidate=candidate,
        ranking=ranking,
        dedupe=dedupe,
        now=now,
    )
    return {
        key: value
        for key, value in data.items()
        if key not in {"first_seen_at", "created_at"}
    } | {
        "status": preserve_status,
        "updated_at": now,
    }


def status_for_imported_listing(score: float, dedupe_status: str) -> str:
    if dedupe_status == "repost":
        return "repost"
    if dedupe_status == "duplicate":
        return "duplicate"
    if score >= 80:
        return "recommended"
    if score >= 40:
        return "new"
    return "trash"


def imported_listing_raw_payload(candidate: dict[str, Any], dedupe: Any, ranking: Any) -> dict[str, Any]:
    return {
        "candidate": candidate,
        "imported_by": "api.listings.import_url",
        "dedupe": dedupe_response(dedupe),
        "ranking": {
            "fit_score": ranking.fit_score,
            "fit_level": ranking.fit_level,
            "factor_scores": dict(ranking.factor_scores),
            "risk_penalty": ranking.risk_penalty,
        },
    }


def dedupe_response(dedupe: Any) -> dict[str, Any]:
    return {
        "status": dedupe.status,
        "matched_listing_id": dedupe.matched_listing_id,
        "score": dedupe.score,
        "reasons": list(dedupe.reasons),
        "similarity": dict(dedupe.similarity),
    }


def contact_packet_response(row: dict[str, Any], *, user_check_id: str | None = None) -> dict[str, Any]:
    payload = {
        "id": row["id"],
        "listing_id": row["listing_id"],
        "status": row["status"],
        "language": row["language"],
        "tone": row["tone"],
        "message_draft": row["message_draft"],
        "questions_to_ask": json_field(row.get("questions_json"), []),
        "dossier_summary": json_field(row.get("dossier_summary_json"), {}),
        "used_at": row.get("used_at"),
        "used_channel": row.get("used_channel"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if user_check_id is not None:
        payload["user_check_id"] = user_check_id
    return payload


def user_check_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "type": row["type"],
        "resource_type": row["resource_type"],
        "resource_id": row["resource_id"],
        "title": row["title"],
        "summary": row["summary"],
        "status": row["status"],
        "payload": json_field(row.get("payload_json"), {}),
        "completed_with": row.get("completed_with"),
        "completed_note": row.get("completed_note"),
        "created_at": row["created_at"],
        "completed_at": row.get("completed_at"),
    }


def notification_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "body": row["body"],
        "resource_type": row.get("resource_type"),
        "resource_id": row.get("resource_id"),
        "read_at": row.get("read_at"),
        "created_at": row["created_at"],
    }


def empty_run_summary() -> dict[str, Any]:
    return {
        "candidate_count": 0,
        "new_count": 0,
        "duplicate_count": 0,
        "repost_count": 0,
        "recommended_count": 0,
        "indexed_count": 0,
        "errors": [],
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


def idempotency_conflict(
    *,
    scope: str,
    idempotency_key: str,
    expected_resource_type: str,
    existing_key: dict[str, Any],
    requested_resource_id: str | None = None,
) -> HTTPException:
    details: dict[str, Any] = {
        "scope": scope,
        "idempotency_key": idempotency_key,
        "expected_resource_type": expected_resource_type,
        "existing_resource_type": existing_key["resource_type"],
        "existing_resource_id": existing_key["resource_id"],
    }
    if requested_resource_id is not None:
        details["requested_resource_id"] = requested_resource_id

    return HTTPException(
        status_code=409,
        detail={
            "code": "idempotency_key_conflict",
            "message": "Cle d'idempotence deja utilisee pour une autre ressource.",
            "details": details,
            "retryable": False,
        },
    )


def idempotency_resource_missing(existing_key: dict[str, Any]) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "idempotency_resource_missing",
            "message": "La ressource associee a cette cle d'idempotence est introuvable.",
            "details": {
                "scope": existing_key["scope"],
                "resource_type": existing_key["resource_type"],
                "resource_id": existing_key["resource_id"],
            },
            "retryable": False,
        },
    )


def auth_not_configured(exc: AuthConfigurationError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "auth_not_configured",
            "message": str(exc),
            "details": {
                "required_env": [
                    "DOSSIERAGENT_SUPABASE_URL",
                    "DOSSIERAGENT_SUPABASE_ANON_KEY",
                ]
            },
            "retryable": False,
        },
    )


def auth_service_exception(exc: AuthServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "retryable": exc.retryable,
        },
    )


class AuthenticatedUserProvisioningError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def auth_provisioning_exception(exc: AuthenticatedUserProvisioningError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "retryable": False,
        },
    )


def provision_auth_session(session: AuthSession) -> AuthSession:
    return replace(session, user=provision_authenticated_user(session.user))


def provision_auth_signup_result(result: AuthSignupResult) -> AuthSignupResult:
    provisioned_user = provision_authenticated_user(result.user) if result.user is not None else None
    provisioned_session = (
        replace(result.session, user=provisioned_user)
        if result.session is not None and provisioned_user is not None
        else None
    )
    return replace(result, user=provisioned_user, session=provisioned_session)


def provision_authenticated_user(auth_user: AuthenticatedUser) -> AuthenticatedUser:
    connection = create_connection()
    try:
        run_migrations(connection)
        repositories = build_repositories(connection)
        now = utc_now()
        user_id = auth_user.app_user_id
        email = auth_user.email or fallback_auth_email(auth_user)
        display_name = auth_user.display_name or auth_user.email or "DossierAgent User"
        password_hash = external_auth_password_hash(auth_user)

        existing_user = repositories.users.find(user_id)
        if existing_user is None:
            email_user = find_user_by_email(connection, email)
            if email_user is not None:
                raise AuthenticatedUserProvisioningError(
                    status_code=403,
                    code="auth_user_conflict",
                    message="Authenticated user maps to an email already owned by another local user.",
                    details={
                        "app_user_id": user_id,
                        "existing_user_id": email_user["id"],
                    },
                )
            repositories.users.create(
                {
                    "id": user_id,
                    "email": email,
                    "password_hash": password_hash,
                    "display_name": display_name,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            connection.commit()
            return auth_user

        updates: dict[str, Any] = {}
        if existing_user["email"] != email:
            if not can_update_external_user_email(existing_user, auth_user):
                raise AuthenticatedUserProvisioningError(
                    status_code=403,
                    code="auth_user_conflict",
                    message="Authenticated user metadata points to an existing local user with a different email.",
                    details={"app_user_id": user_id},
                )
            email_user = find_user_by_email(connection, email)
            if email_user is not None and email_user["id"] != user_id:
                raise AuthenticatedUserProvisioningError(
                    status_code=403,
                    code="auth_user_conflict",
                    message="Authenticated email is already linked to another local user.",
                    details={
                        "app_user_id": user_id,
                        "existing_user_id": email_user["id"],
                    },
                )
            updates["email"] = email
        if existing_user["display_name"] != display_name:
            updates["display_name"] = display_name
        if existing_user["password_hash"].startswith(EXTERNAL_AUTH_PASSWORD_HASH_PREFIX):
            updates["password_hash"] = password_hash
        if updates:
            updates["updated_at"] = now
            repositories.users.update(user_id, updates)
            connection.commit()
        return auth_user
    finally:
        connection.close()


def external_auth_password_hash(auth_user: AuthenticatedUser) -> str:
    return f"{EXTERNAL_AUTH_PASSWORD_HASH_PREFIX}:{auth_user.provider}:{auth_user.provider_user_id}"


def fallback_auth_email(auth_user: AuthenticatedUser) -> str:
    return f"{auth_user.app_user_id}@{auth_user.provider}.auth.local"


def find_user_by_email(connection: Any, email: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM users WHERE email = ? LIMIT 1", (email,)).fetchone()
    return None if row is None else {key: row[key] for key in row.keys()}


def can_update_external_user_email(
    existing_user: dict[str, Any],
    auth_user: AuthenticatedUser,
) -> bool:
    return existing_user["password_hash"] == external_auth_password_hash(auth_user)


def auth_session_response(session: AuthSession) -> dict[str, Any]:
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": session.token_type,
        "expires_in": session.expires_in,
        "expires_at": session.expires_at,
        "user": auth_user_response(session.user),
    }


def auth_signup_result_response(result: AuthSignupResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "user": auth_user_response(result.user) if result.user is not None else None,
        "session": auth_session_response(result.session) if result.session is not None else None,
    }


def auth_user_response(auth_user: AuthenticatedUser) -> dict[str, Any]:
    return {
        "provider": auth_user.provider,
        "provider_user_id": auth_user.provider_user_id,
        "app_user_id": auth_user.app_user_id,
        "email": auth_user.email,
        "display_name": auth_user.display_name,
    }


def request_user_id(header_user_id: str | None) -> str:
    auth_user = current_auth_user()
    if auth_user is not None:
        return auth_user.app_user_id
    return header_user_id or os.environ.get("DOSSIERAGENT_DEMO_USER_ID", DEFAULT_DEMO_USER_ID)


def normalize_optional_header(value: str | None) -> str | None:
    if value is None:
        return None
    stripped_value = value.strip()
    return stripped_value or None


def resolve_storage_path() -> Path:
    return Path(os.environ.get("DOSSIERAGENT_STORAGE_PATH", "storage"))


def clean_form_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip().replace("\x00", "")
    if not name:
        return "document.pdf"
    safe = "".join(character if character.isalnum() or character in "._- " else "_" for character in name)
    return safe.strip(" .") or "document.pdf"


def is_pdf_upload(filename: str, content_type: str | None) -> bool:
    clean_content_type = (content_type or "").split(";")[0].strip().lower()
    return clean_content_type == "application/pdf" or filename.lower().endswith(".pdf")


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
        headers=elastic_headers(content_type="application/json"),
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


def attach_search_index_summary(
    connection: Any,
    repositories: Any,
    *,
    run: dict[str, Any],
    user_id: str,
    watch_id: str,
    now: str,
) -> dict[str, Any]:
    summary = json_field(run["summary_json"], empty_run_summary())
    summary["search_index"] = index_watch_listings(
        connection,
        user_id=user_id,
        watch_id=watch_id,
    )
    return repositories.agent_runs.update(
        run["id"],
        {
            "summary_json": json_data(summary),
            "updated_at": now,
        },
    )


def index_watch_listings(
    connection: Any,
    *,
    user_id: str,
    watch_id: str,
) -> dict[str, Any]:
    rows = list_listing_rows_for_watch(connection, user_id=user_id, watch_id=watch_id)
    if not rows:
        return {
            "status": "skipped",
            "reason": "no_listings",
            "attempted": 0,
            "indexed": 0,
            "errors": [],
        }
    return index_elastic_listings(rows)


def index_elastic_listings(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    index_name = os.environ.get("DOSSIERAGENT_ELASTIC_LISTINGS_INDEX", "listings_v1")
    elastic_url = normalize_optional_header(os.environ.get("DOSSIERAGENT_ELASTIC_URL"))
    if elastic_url is None:
        return {
            "status": "skipped",
            "reason": "elastic_not_configured",
            "index": index_name,
            "attempted": len(rows),
            "indexed": 0,
            "errors": [],
        }

    bulk_payload = build_listing_bulk_ndjson(index_name=index_name, listings=rows)
    if not bulk_payload:
        return {
            "status": "skipped",
            "reason": "no_listings",
            "index": index_name,
            "attempted": 0,
            "indexed": 0,
            "errors": [],
        }

    request = urllib.request.Request(
        f"{elastic_url.rstrip('/')}/_bulk",
        data=bulk_payload,
        method="POST",
        headers=elastic_headers(content_type="application/x-ndjson"),
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "status": "skipped",
            "reason": "elastic_unavailable",
            "index": index_name,
            "attempted": len(rows),
            "indexed": 0,
            "errors": [{"type": type(exc).__name__, "message": str(exc)}],
        }

    return parse_bulk_index_response(
        index_name=index_name,
        attempted=len(rows),
        payload=payload,
    ).as_dict()


def list_listing_rows_for_watch(
    connection: Any,
    *,
    user_id: str,
    watch_id: str,
) -> tuple[dict[str, Any], ...]:
    rows = connection.execute(
        """
        SELECT * FROM listings
        WHERE user_id = ? AND watch_id = ?
        ORDER BY first_seen_at DESC, id ASC
        """,
        (user_id, watch_id),
    ).fetchall()
    return tuple({key: row[key] for key in row.keys()} for row in rows)


def elastic_headers(*, content_type: str) -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": content_type}
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


def authorize_internal_browser_request(request: Request, authorization: str | None) -> str:
    configured_secret = normalize_optional_header(os.environ.get("DOSSIERAGENT_BROWSER_INTERNAL_SECRET"))
    clean_authorization = normalize_optional_header(authorization)
    if configured_secret is not None:
        if clean_authorization == f"Bearer {configured_secret}":
            return "secret"
        raise HTTPException(
            status_code=403,
            detail={
                "code": "browser_internal_secret_required",
                "message": "Secret navigateur interne invalide ou manquant.",
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
            "code": "browser_internal_local_only",
            "message": "Route navigateur interne limitee aux appels locaux quand aucun secret n'est configure.",
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

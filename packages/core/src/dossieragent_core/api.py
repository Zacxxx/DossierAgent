from __future__ import annotations

import argparse
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request
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


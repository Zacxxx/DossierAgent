from __future__ import annotations

import hashlib
import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    provider: str
    provider_user_id: str
    app_user_id: str
    email: str | None
    display_name: str | None
    raw_user: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SupabaseAuthSettings:
    url: str
    anon_key: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class AuthSession:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int | None
    expires_at: int | None
    user: AuthenticatedUser


@dataclass(frozen=True, slots=True)
class AuthSignupResult:
    status: str
    user: AuthenticatedUser | None
    session: AuthSession | None


class AuthConfigurationError(RuntimeError):
    pass


class AuthServiceError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable


_current_auth_user: ContextVar[AuthenticatedUser | None] = ContextVar(
    "dossieragent_auth_user",
    default=None,
)


def set_current_auth_user(user: AuthenticatedUser | None) -> Token[AuthenticatedUser | None]:
    return _current_auth_user.set(user)


def reset_current_auth_user(token: Token[AuthenticatedUser | None]) -> None:
    _current_auth_user.reset(token)


def current_auth_user() -> AuthenticatedUser | None:
    return _current_auth_user.get()


def load_supabase_settings() -> SupabaseAuthSettings | None:
    url = os.environ.get("DOSSIERAGENT_SUPABASE_URL", "").strip().rstrip("/")
    anon_key = os.environ.get("DOSSIERAGENT_SUPABASE_ANON_KEY", "").strip()
    if not url and not anon_key:
        return None
    if not url or not anon_key:
        raise AuthConfigurationError(
            "Both DOSSIERAGENT_SUPABASE_URL and DOSSIERAGENT_SUPABASE_ANON_KEY are required."
        )
    timeout_seconds = float(os.environ.get("DOSSIERAGENT_SUPABASE_TIMEOUT_SECONDS", "8"))
    return SupabaseAuthSettings(url=url, anon_key=anon_key, timeout_seconds=timeout_seconds)


def auth_required() -> bool:
    value = os.environ.get("DOSSIERAGENT_AUTH_REQUIRED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def bearer_token_from_authorization(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


class SupabaseAuthClient:
    def __init__(self, settings: SupabaseAuthSettings) -> None:
        self.settings = settings

    def login(self, *, email: str, password: str) -> AuthSession:
        payload = self._request(
            "POST",
            "/auth/v1/token",
            params={"grant_type": "password"},
            json={"email": email, "password": password},
            error_code="invalid_credentials",
            error_message="Email ou mot de passe invalide.",
        )
        return auth_session_from_payload(payload)

    def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
        redirect_to: str | None = None,
    ) -> AuthSignupResult:
        data: dict[str, Any] = {}
        if display_name:
            data["display_name"] = display_name
        request_payload: dict[str, Any] = {"email": email, "password": password}
        if data:
            request_payload["data"] = data
        payload = self._request(
            "POST",
            "/auth/v1/signup",
            params={"redirect_to": redirect_to} if redirect_to else None,
            json=request_payload,
            error_code="registration_failed",
            error_message="Inscription impossible.",
        )
        return auth_signup_result_from_payload(payload)

    def refresh(self, *, refresh_token: str) -> AuthSession:
        payload = self._request(
            "POST",
            "/auth/v1/token",
            params={"grant_type": "refresh_token"},
            json={"refresh_token": refresh_token},
            error_code="invalid_refresh_token",
            error_message="Refresh token invalide ou expire.",
        )
        return auth_session_from_payload(payload)

    def get_user(self, *, access_token: str) -> AuthenticatedUser:
        payload = self._request(
            "GET",
            "/auth/v1/user",
            access_token=access_token,
            error_code="invalid_access_token",
            error_message="Token d'acces invalide ou expire.",
        )
        return authenticated_user_from_payload(payload)

    def recover_password(self, *, email: str, redirect_to: str | None = None) -> None:
        self._request(
            "POST",
            "/auth/v1/recover",
            params={"redirect_to": redirect_to} if redirect_to else None,
            json={"email": email},
            error_code="password_recovery_failed",
            error_message="Demande de reinitialisation impossible.",
            empty_ok=True,
        )

    def logout(self, *, access_token: str) -> None:
        self._request(
            "POST",
            "/auth/v1/logout",
            access_token=access_token,
            error_code="logout_failed",
            error_message="Deconnexion impossible.",
            empty_ok=True,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        error_code: str,
        error_message: str,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        access_token: str | None = None,
        empty_ok: bool = False,
    ) -> dict[str, Any]:
        headers = {
            "apikey": self.settings.anon_key,
            "Accept": "application/json",
        }
        if access_token is not None:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            response = httpx.request(
                method,
                f"{self.settings.url}{path}",
                params=params,
                json=json,
                headers=headers,
                timeout=self.settings.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise AuthServiceError(
                status_code=503,
                code="auth_provider_timeout",
                message="Supabase Auth n'a pas repondu a temps.",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AuthServiceError(
                status_code=503,
                code="auth_provider_unavailable",
                message="Supabase Auth est indisponible.",
                details={"error": str(exc)},
                retryable=True,
            ) from exc

        if response.status_code >= 400:
            details = parse_error_details(response)
            raise AuthServiceError(
                status_code=401 if response.status_code in {400, 401, 403} else response.status_code,
                code=error_code,
                message=error_message,
                details=details,
                retryable=response.status_code >= 500,
            )

        if not response.content and empty_ok:
            return {}
        payload = response.json()
        if not isinstance(payload, dict):
            raise AuthServiceError(
                status_code=502,
                code="auth_provider_invalid_response",
                message="Supabase Auth a retourne une reponse invalide.",
                retryable=True,
            )
        return payload


def build_auth_client() -> SupabaseAuthClient:
    settings = load_supabase_settings()
    if settings is None:
        raise AuthConfigurationError(
            "Supabase Auth is not configured. Set DOSSIERAGENT_SUPABASE_URL and "
            "DOSSIERAGENT_SUPABASE_ANON_KEY."
        )
    return SupabaseAuthClient(settings)


def auth_session_from_payload(payload: dict[str, Any]) -> AuthSession:
    access_token = require_string(payload, "access_token")
    refresh_token = require_string(payload, "refresh_token")
    token_type = str(payload.get("token_type") or "bearer")
    user_payload = payload.get("user")
    if not isinstance(user_payload, dict):
        raise AuthServiceError(
            status_code=502,
            code="auth_provider_invalid_response",
            message="Supabase Auth did not return a user profile.",
            retryable=True,
        )
    return AuthSession(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type,
        expires_in=optional_int(payload.get("expires_in")),
        expires_at=optional_int(payload.get("expires_at")),
        user=authenticated_user_from_payload(user_payload),
    )


def auth_signup_result_from_payload(payload: dict[str, Any]) -> AuthSignupResult:
    if payload.get("access_token"):
        session = auth_session_from_payload(payload)
        return AuthSignupResult(status="session_created", user=session.user, session=session)
    user_payload = payload.get("user")
    if isinstance(user_payload, dict):
        return AuthSignupResult(
            status="confirmation_required",
            user=authenticated_user_from_payload(user_payload),
            session=None,
        )
    return AuthSignupResult(status="confirmation_required", user=None, session=None)


def authenticated_user_from_payload(payload: dict[str, Any]) -> AuthenticatedUser:
    provider_user_id = require_string(payload, "id")
    email = optional_string(payload.get("email"))
    user_metadata = payload.get("user_metadata")
    app_metadata = payload.get("app_metadata")
    user_metadata = user_metadata if isinstance(user_metadata, dict) else {}
    app_metadata = app_metadata if isinstance(app_metadata, dict) else {}
    app_user_id = validated_app_user_id(
        optional_string(app_metadata.get("dossieragent_user_id"))
        or optional_string(user_metadata.get("dossieragent_user_id"))
    )
    display_name = (
        optional_string(user_metadata.get("display_name"))
        or optional_string(user_metadata.get("full_name"))
        or optional_string(user_metadata.get("name"))
        or email
    )
    return AuthenticatedUser(
        provider="supabase",
        provider_user_id=provider_user_id,
        app_user_id=app_user_id or derived_app_user_id("supabase", provider_user_id),
        email=email,
        display_name=display_name,
        raw_user=payload,
    )


def derived_app_user_id(provider: str, provider_user_id: str) -> str:
    digest = hashlib.sha256(f"{provider}:{provider_user_id}".encode("utf-8")).hexdigest()[:20]
    safe_provider = "".join(character for character in provider.lower() if character.isalnum())[:16]
    return f"usr_{safe_provider}_{digest}"


def validated_app_user_id(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.startswith("usr_"):
        return None
    if not value.replace("_", "").replace("-", "").replace(":", "").isalnum():
        return None
    return value


def require_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise AuthServiceError(
            status_code=502,
            code="auth_provider_invalid_response",
            message=f"Supabase Auth response is missing `{field_name}`.",
            retryable=True,
        )
    return value.strip()


def optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_error_details(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {"status_code": response.status_code}
    if not isinstance(payload, dict):
        return {"status_code": response.status_code}
    return {
        key: value
        for key, value in payload.items()
        if key in {"error", "error_description", "msg", "message", "code"}
    } | {"status_code": response.status_code}

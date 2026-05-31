from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


SECRET_STORE_VERSION = 1
AI_PROVIDER_FIELDS = {
    "openai": {"api_key"},
    "anthropic": {"api_key"},
    "google": {"api_key"},
    "codex": {"provider_path", "provider_mode"},
}


class SecretStoreError(RuntimeError):
    pass


def get_ai_provider_secret(provider_id: str, field_name: str) -> str | None:
    return load_secret_store().get("providers", {}).get(provider_id, {}).get(field_name)


def set_ai_provider_secrets(
    provider_id: str,
    values: dict[str, str | None],
    *,
    clear_fields: set[str] | None = None,
) -> dict[str, Any]:
    if provider_id not in AI_PROVIDER_FIELDS:
        raise ValueError(f"Unknown AI provider: {provider_id}")
    allowed_fields = AI_PROVIDER_FIELDS[provider_id]
    store = load_secret_store()
    providers = store.setdefault("providers", {})
    provider = providers.setdefault(provider_id, {})

    for field_name in clear_fields or set():
        if field_name in allowed_fields:
            provider.pop(field_name, None)

    for field_name, value in values.items():
        if field_name not in allowed_fields:
            continue
        if value is None or not str(value).strip():
            continue
        provider[field_name] = str(value).strip()

    if not provider:
        providers.pop(provider_id, None)
    write_secret_store(store)
    return redacted_ai_provider_settings()


def redacted_ai_provider_settings() -> dict[str, Any]:
    providers = load_secret_store().get("providers", {})
    return {
        "providers": [
            {
                "id": provider_id,
                "stored_fields": sorted(providers.get(provider_id, {}).keys()),
                "env_fields": sorted(env_configured_fields(provider_id)),
            }
            for provider_id in AI_PROVIDER_FIELDS
        ]
    }


def env_configured_fields(provider_id: str) -> set[str]:
    if provider_id == "openai" and os.environ.get("DOSSIERAGENT_OPENAI_API_KEY", "").strip():
        return {"api_key"}
    if provider_id == "anthropic" and os.environ.get("DOSSIERAGENT_ANTHROPIC_API_KEY", "").strip():
        return {"api_key"}
    if provider_id == "google" and os.environ.get("DOSSIERAGENT_GOOGLE_API_KEY", "").strip():
        return {"api_key"}
    fields: set[str] = set()
    if provider_id == "codex":
        if os.environ.get("DOSSIERAGENT_CODEX_PROVIDER_PATH", "").strip():
            fields.add("provider_path")
        if os.environ.get("DOSSIERAGENT_CODEX_PROVIDER_MODE", "").strip():
            fields.add("provider_mode")
    return fields


def load_secret_store() -> dict[str, Any]:
    path = secret_store_path()
    if not path.exists():
        return {"version": SECRET_STORE_VERSION, "providers": {}}
    try:
        decrypted = fernet().decrypt(path.read_bytes())
        payload = json.loads(decrypted.decode("utf-8"))
    except (InvalidToken, OSError, json.JSONDecodeError) as exc:
        raise SecretStoreError("Secret store is unreadable or was encrypted with a different key.") from exc
    if not isinstance(payload, dict):
        raise SecretStoreError("Secret store payload is invalid.")
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        payload["providers"] = {}
    payload["version"] = SECRET_STORE_VERSION
    return payload


def write_secret_store(payload: dict[str, Any]) -> None:
    path = secret_store_path()
    ensure_secret_parent(path)
    encrypted = fernet().encrypt(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8"))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encrypted)
    finally:
        path.chmod(0o600)


def secret_store_path() -> Path:
    configured = os.environ.get("DOSSIERAGENT_SECRET_STORE_PATH", "").strip()
    if configured:
        return Path(configured)
    storage_root = Path(os.environ.get("DOSSIERAGENT_STORAGE_PATH", "storage"))
    return storage_root / "secrets" / "ai-provider-secrets.json.enc"


def fernet() -> Fernet:
    key = os.environ.get("DOSSIERAGENT_SECRETS_KEY", "").strip()
    if key:
        return Fernet(key.encode("utf-8"))
    key_path = secret_key_path()
    ensure_secret_parent(key_path)
    if key_path.exists():
        key = key_path.read_text(encoding="utf-8").strip()
    else:
        key = Fernet.generate_key().decode("utf-8")
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(key)
        finally:
            key_path.chmod(0o600)
    return Fernet(key.encode("utf-8"))


def secret_key_path() -> Path:
    configured = os.environ.get("DOSSIERAGENT_SECRETS_KEY_PATH", "").strip()
    if configured:
        return Path(configured)
    return secret_store_path().with_name("master.key")


def ensure_secret_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)

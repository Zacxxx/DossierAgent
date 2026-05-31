from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from dossieragent_core.secret_store import get_ai_provider_secret


DEFAULT_TIMEOUT_SECONDS = 20.0
ANTHROPIC_VERSION = "2023-06-01"


class AIProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class AIMessage:
    role: str
    content: str


def provider_statuses() -> list[dict[str, Any]]:
    return [
        openai_status(),
        anthropic_status(),
        google_status(),
        codex_status(),
    ]


def chat_completion(provider: str, model: str, messages: list[AIMessage]) -> dict[str, Any]:
    normalized_provider = provider.strip().lower()
    if normalized_provider == "openai":
        content, usage = openai_chat_completion(model=model, messages=messages)
    elif normalized_provider == "anthropic":
        content, usage = anthropic_chat_completion(model=model, messages=messages)
    elif normalized_provider == "google":
        content, usage = google_chat_completion(model=model, messages=messages)
    elif normalized_provider == "codex":
        content, usage = codex_chat_completion(model=model, messages=messages)
    else:
        raise AIProviderError(
            "unknown_ai_provider",
            "Fournisseur IA inconnu.",
            status_code=400,
            details={"provider": provider},
        )
    return {
        "provider": normalized_provider,
        "model": model,
        "message": {"role": "assistant", "content": content},
        "usage": usage,
    }


def openai_status() -> dict[str, Any]:
    api_key = ai_secret("openai", "api_key", "DOSSIERAGENT_OPENAI_API_KEY")
    if not api_key:
        return unavailable_provider("openai", "OpenAI", "DOSSIERAGENT_OPENAI_API_KEY")
    try:
        payload = request_json(
            f"{openai_base_url()}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        models = [
            {
                "id": item["id"],
                "label": item["id"],
                "owned_by": item.get("owned_by"),
            }
            for item in payload.get("data", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        return configured_provider("openai", "OpenAI", models=models, model_source="api")
    except AIProviderError as exc:
        return errored_provider("openai", "OpenAI", exc)


def anthropic_status() -> dict[str, Any]:
    api_key = ai_secret("anthropic", "api_key", "DOSSIERAGENT_ANTHROPIC_API_KEY")
    if not api_key:
        return unavailable_provider("anthropic", "Anthropic", "DOSSIERAGENT_ANTHROPIC_API_KEY")
    try:
        payload = request_json(
            f"{anthropic_base_url()}/models",
            headers=anthropic_headers(api_key),
        )
        models = [
            {
                "id": item["id"],
                "label": item.get("display_name") or item["id"],
                "created_at": item.get("created_at"),
            }
            for item in payload.get("data", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        return configured_provider("anthropic", "Anthropic", models=models, model_source="api")
    except AIProviderError as exc:
        return errored_provider("anthropic", "Anthropic", exc)


def google_status() -> dict[str, Any]:
    api_key = ai_secret("google", "api_key", "DOSSIERAGENT_GOOGLE_API_KEY")
    if not api_key:
        return unavailable_provider("google", "Google Gemini", "DOSSIERAGENT_GOOGLE_API_KEY")
    try:
        payload = request_json(
            f"{google_base_url()}/models?{urlencode({'key': api_key, 'pageSize': 1000})}",
            headers={},
        )
        models = []
        for item in payload.get("models", []):
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            supported = item.get("supportedGenerationMethods", [])
            if isinstance(supported, list) and supported and "generateContent" not in supported:
                continue
            models.append(
                {
                    "id": str(item.get("baseModelId") or item["name"]).removeprefix("models/"),
                    "label": item.get("displayName") or item["name"],
                    "name": item["name"],
                }
            )
        return configured_provider("google", "Google Gemini", models=models, model_source="api")
    except AIProviderError as exc:
        return errored_provider("google", "Google Gemini", exc)


def codex_status() -> dict[str, Any]:
    codex_path = ai_secret("codex", "provider_path", "DOSSIERAGENT_CODEX_PROVIDER_PATH")
    if not codex_path:
        return unavailable_provider("codex", "Codex", "DOSSIERAGENT_CODEX_PROVIDER_PATH")
    configured = Path(codex_path).exists()
    return {
        "id": "codex",
        "label": "Codex",
        "configured": configured,
        "model_source": "local_path",
        "models": [],
        "error": None if configured else "codex_path_not_found",
        "details": {
            "path": codex_path if configured else None,
            "mode": codex_provider_mode(codex_path) if configured else None,
        },
    }


def openai_chat_completion(*, model: str, messages: list[AIMessage]) -> tuple[str, dict[str, Any] | None]:
    api_key = required_ai_secret("openai", "api_key", "DOSSIERAGENT_OPENAI_API_KEY")
    payload = request_json(
        f"{openai_base_url()}/chat/completions",
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload={
            "model": model,
            "messages": [message_payload(message) for message in messages],
            "temperature": 0.2,
            "max_tokens": 1024,
        },
    )
    choices = payload.get("choices", [])
    if not choices:
        raise AIProviderError("empty_ai_response", "OpenAI n'a renvoye aucun choix.")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    return str(message.get("content") or ""), payload.get("usage")


def anthropic_chat_completion(*, model: str, messages: list[AIMessage]) -> tuple[str, dict[str, Any] | None]:
    api_key = required_ai_secret("anthropic", "api_key", "DOSSIERAGENT_ANTHROPIC_API_KEY")
    system_prompt, conversation = split_system_messages(messages)
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 1024,
        "messages": [message_payload(message) for message in conversation if message.role != "system"],
    }
    if system_prompt:
        payload["system"] = system_prompt
    response = request_json(
        f"{anthropic_base_url()}/messages",
        method="POST",
        headers=anthropic_headers(api_key) | {"Content-Type": "application/json"},
        payload=payload,
    )
    content_blocks = response.get("content", [])
    text = "\n".join(
        block.get("text", "")
        for block in content_blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    return text, response.get("usage")


def google_chat_completion(*, model: str, messages: list[AIMessage]) -> tuple[str, dict[str, Any] | None]:
    api_key = required_ai_secret("google", "api_key", "DOSSIERAGENT_GOOGLE_API_KEY")
    system_prompt, conversation = split_system_messages(messages)
    model_name = model if model.startswith("models/") else f"models/{model}"
    payload: dict[str, Any] = {
        "contents": [
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
            for message in conversation
            if message.role != "system"
        ]
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    response = request_json(
        f"{google_base_url()}/{quote(model_name, safe='/')}:generateContent?{urlencode({'key': api_key})}",
        method="POST",
        headers={"Content-Type": "application/json"},
        payload=payload,
    )
    candidates = response.get("candidates", [])
    if not candidates:
        raise AIProviderError("empty_ai_response", "Google Gemini n'a renvoye aucun candidat.")
    parts = candidates[0].get("content", {}).get("parts", []) if isinstance(candidates[0], dict) else []
    text = "\n".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ).strip()
    return text, response.get("usageMetadata")


def codex_chat_completion(*, model: str, messages: list[AIMessage]) -> tuple[str, dict[str, Any] | None]:
    codex_path = required_ai_secret("codex", "provider_path", "DOSSIERAGENT_CODEX_PROVIDER_PATH")
    if not Path(codex_path).exists():
        raise AIProviderError(
            "codex_path_not_found",
            "Le chemin Codex configure est introuvable.",
            status_code=503,
        )
    if codex_provider_mode(codex_path) == "codex_cli":
        return codex_cli_chat_completion(codex_path=codex_path, model=model, messages=messages)

    input_payload = json.dumps(
        {"model": model, "messages": [message_payload(message) for message in messages]},
        ensure_ascii=True,
    )
    try:
        completed = subprocess.run(
            [codex_path],
            input=input_payload,
            text=True,
            capture_output=True,
            timeout=float(os.environ.get("DOSSIERAGENT_CODEX_TIMEOUT_SECONDS", "60")),
            check=False,
        )
    except OSError as exc:
        raise AIProviderError("codex_launch_failed", str(exc), status_code=503) from exc
    except subprocess.TimeoutExpired as exc:
        raise AIProviderError("codex_timeout", "Codex provider timeout.", retryable=True) from exc
    if completed.returncode != 0:
        raise AIProviderError(
            "codex_provider_failed",
            completed.stderr.strip() or "Codex provider failed.",
            retryable=False,
        )
    return completed.stdout.strip(), None


def codex_provider_mode(codex_path: str) -> str:
    configured_mode = ai_secret("codex", "provider_mode", "DOSSIERAGENT_CODEX_PROVIDER_MODE")
    if configured_mode:
        return configured_mode
    return "codex_cli" if Path(codex_path).name == "codex" else "json_stdio"


def codex_cli_chat_completion(
    *,
    codex_path: str,
    model: str,
    messages: list[AIMessage],
) -> tuple[str, dict[str, Any] | None]:
    prompt = render_codex_prompt(messages)
    output_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="dossieragent-codex-", suffix=".txt", delete=False) as output:
            output_path = output.name
        args = [
            codex_path,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--output-last-message",
            output_path,
        ]
        if model and model not in {"tool-router", "codex-default", "default"}:
            args.extend(["--model", model])
        args.append(prompt)
        completed = subprocess.run(
            args,
            text=True,
            capture_output=True,
            timeout=float(os.environ.get("DOSSIERAGENT_CODEX_TIMEOUT_SECONDS", "120")),
            check=False,
        )
        if completed.returncode != 0:
            raise AIProviderError(
                "codex_provider_failed",
                completed.stderr.strip() or "Codex CLI provider failed.",
                retryable=False,
            )
        content = Path(output_path).read_text(encoding="utf-8").strip()
        return content or completed.stdout.strip(), None
    except OSError as exc:
        raise AIProviderError("codex_launch_failed", str(exc), status_code=503) from exc
    except subprocess.TimeoutExpired as exc:
        raise AIProviderError("codex_timeout", "Codex provider timeout.", retryable=True) from exc
    finally:
        if output_path is not None:
            Path(output_path).unlink(missing_ok=True)


def render_codex_prompt(messages: list[AIMessage]) -> str:
    rendered = []
    for message in messages:
        rendered.append(f"{message.role.upper()}: {message.content}")
    return "\n\n".join(rendered)


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(
            request,
            timeout=float(os.environ.get("DOSSIERAGENT_AI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
        ) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AIProviderError(
            "ai_provider_http_error",
            f"Provider returned HTTP {exc.code}.",
            retryable=exc.code >= 500,
            details={"status_code": exc.code},
        ) from exc
    except urllib.error.URLError as exc:
        raise AIProviderError(
            "ai_provider_unreachable",
            str(exc.reason),
            retryable=True,
        ) from exc
    except json.JSONDecodeError as exc:
        raise AIProviderError("ai_provider_invalid_json", "Provider returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise AIProviderError("ai_provider_invalid_json", "Provider returned an invalid payload.")
    return decoded


def configured_provider(
    provider_id: str,
    label: str,
    *,
    models: list[dict[str, Any]],
    model_source: str,
) -> dict[str, Any]:
    return {
        "id": provider_id,
        "label": label,
        "configured": True,
        "model_source": model_source,
        "models": models,
        "error": None,
        "details": {},
    }


def unavailable_provider(provider_id: str, label: str, env_var: str) -> dict[str, Any]:
    return {
        "id": provider_id,
        "label": label,
        "configured": False,
        "model_source": "api",
        "models": [],
        "error": "missing_secret",
        "details": {"env_var": env_var},
    }


def errored_provider(provider_id: str, label: str, error: AIProviderError) -> dict[str, Any]:
    return {
        "id": provider_id,
        "label": label,
        "configured": True,
        "model_source": "api",
        "models": [],
        "error": error.code,
        "details": {"message": error.message, **error.details},
    }


def ai_secret(provider: str, field_name: str, env_var: str) -> str:
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return env_value
    return get_ai_provider_secret(provider, field_name) or ""


def required_ai_secret(provider: str, field_name: str, env_var: str) -> str:
    value = ai_secret(provider, field_name, env_var)
    if value:
        return value
    raise AIProviderError(
        "missing_ai_secret",
        f"{env_var} n'est pas configure.",
        status_code=503,
        details={"provider": provider, "env_var": env_var},
    )


def required_env(env_var: str, provider: str) -> str:
    value = os.environ.get(env_var, "").strip()
    if value:
        return value
    raise AIProviderError(
        "missing_ai_secret",
        f"{env_var} n'est pas configure.",
        status_code=503,
        details={"provider": provider, "env_var": env_var},
    )


def message_payload(message: AIMessage) -> dict[str, str]:
    return {"role": message.role, "content": message.content}


def split_system_messages(messages: list[AIMessage]) -> tuple[str | None, list[AIMessage]]:
    system_messages = [message.content for message in messages if message.role == "system"]
    conversation = [message for message in messages if message.role != "system"]
    return ("\n\n".join(system_messages) if system_messages else None, conversation)


def openai_base_url() -> str:
    return os.environ.get("DOSSIERAGENT_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def anthropic_base_url() -> str:
    return os.environ.get("DOSSIERAGENT_ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")


def google_base_url() -> str:
    return os.environ.get(
        "DOSSIERAGENT_GOOGLE_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta",
    ).rstrip("/")


def anthropic_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": os.environ.get("DOSSIERAGENT_ANTHROPIC_VERSION", ANTHROPIC_VERSION),
    }

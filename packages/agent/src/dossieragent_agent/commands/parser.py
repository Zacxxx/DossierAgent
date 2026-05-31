from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CommandStatus = Literal["accepted", "rejected"]

BLOCKED_CONTACT_PATTERNS = (
    "send email",
    "send mail",
    "email landlord",
    "mail landlord",
    "contact landlord",
    "send message",
    "envoie un email",
    "envoie un mail",
    "envoie le message",
    "contacte le proprietaire",
    "contacte l agence",
    "appelle l agence",
)

CITY_PATTERN = re.compile(r"\b(?:a|à|pour|in|sur)\s+([a-z][a-z -]{1,40})")
BUDGET_PATTERN = re.compile(r"(?:budget|loyer|rent|under|moins de|max(?:imum)?)\s*(?:de|than|a|à)?\s*(\d{2,5})")
ROOMS_PATTERN = re.compile(r"\b(?:t|f|rooms?|pieces?|pi[eè]ces?)\s*([1-6])\b")
WATCH_ID_PATTERN = re.compile(r"\bwatch_[a-z0-9_:-]+\b")


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    status: CommandStatus
    intent: str
    action: str
    summary: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    guardrails: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["parameters"] = dict(self.parameters)
        payload["guardrails"] = list(self.guardrails)
        return payload


def parse_command(command: str, *, context: Mapping[str, Any] | None = None) -> ParsedCommand:
    original = command.strip()
    normalized = normalize_text(original)
    context = context or {}

    if not original:
        return reject("empty_command", "La commande est vide.", guardrails=("command_required",))

    if contains_any(normalized, BLOCKED_CONTACT_PATTERNS):
        return reject(
            "blocked_external_contact",
            "Contact externe autonome refuse. Preparez un paquet de contact pour validation humaine.",
            guardrails=("no_autonomous_email", "human_review_required"),
        )

    if contains_any(normalized, ("scan", "run", "lance", "lancer", "cherche", "chercher")) and contains_any(
        normalized,
        ("veille", "watch", "annonce", "annonces"),
    ):
        watch_id = string_context(context, "watch_id") or regex_value(WATCH_ID_PATTERN, normalized)
        return accept(
            intent="run_market_watch",
            action="run_watch_now",
            summary="Lancer une veille et creer un run supervise.",
            parameters={"watch_id": watch_id},
            guardrails=("no_external_contact",),
        )

    if contains_any(normalized, ("analyse", "analyser", "analyze", "recalcule", "readiness", "completude")) and contains_any(
        normalized,
        ("dossier", "documents", "pieces"),
    ):
        return accept(
            intent="analyze_dossier",
            action="create_dossier_snapshot",
            summary="Recalculer la completude du dossier.",
            guardrails=("local_documents_only",),
        )

    if contains_any(normalized, ("affiche", "montre", "show", "liste", "list")) and contains_any(
        normalized,
        ("annonces", "listings", "recommand"),
    ):
        return accept(
            intent="show_recommended_listings",
            action="list_recommended_listings",
            summary="Afficher les annonces recommandees.",
        )

    if contains_any(normalized, ("cree", "creer", "create", "nouvelle")) and contains_any(
        normalized,
        ("veille", "watch"),
    ):
        city = string_context(context, "city") or parse_city(normalized)
        budget_max = number_context(context, "budget_max") or parse_number(BUDGET_PATTERN, normalized)
        rooms_min = number_context(context, "rooms_min") or parse_number(ROOMS_PATTERN, normalized)
        if city is None:
            return reject(
                "create_watch_missing_city",
                "La ville est requise pour creer une veille.",
                guardrails=("structured_criteria_required",),
            )
        parameters: dict[str, Any] = {
            "city": title_case_city(city),
            "budget_max": budget_max,
            "rooms_min": rooms_min,
            "frequency": string_context(context, "frequency") or "daily",
        }
        return accept(
            intent="create_market_watch",
            action="create_watch",
            summary="Creer une veille a partir de criteres simples.",
            parameters=parameters,
            guardrails=("structured_criteria_only",),
        )

    return reject(
        "unsupported_command",
        "Commande non reconnue par l'interpreteur supervise.",
        guardrails=("supported_intents_only",),
    )


def accept(
    *,
    intent: str,
    action: str,
    summary: str,
    parameters: Mapping[str, Any] | None = None,
    guardrails: tuple[str, ...] = (),
) -> ParsedCommand:
    return ParsedCommand(
        status="accepted",
        intent=intent,
        action=action,
        summary=summary,
        parameters=parameters or {},
        guardrails=guardrails,
    )


def reject(intent: str, summary: str, *, guardrails: tuple[str, ...]) -> ParsedCommand:
    return ParsedCommand(
        status="rejected",
        intent=intent,
        action="none",
        summary=summary,
        guardrails=guardrails,
    )


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def string_context(context: Mapping[str, Any], key: str) -> str | None:
    value = context.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def number_context(context: Mapping[str, Any], key: str) -> float | None:
    value = context.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def regex_value(pattern: re.Pattern[str], value: str) -> str | None:
    match = pattern.search(value)
    return match.group(0) if match else None


def parse_number(pattern: re.Pattern[str], value: str) -> float | None:
    match = pattern.search(value)
    if match is None:
        return None
    return float(match.group(1))


def parse_city(value: str) -> str | None:
    match = CITY_PATTERN.search(value)
    if match is None:
        return None
    candidate = match.group(1)
    candidate = re.split(r"\b(?:budget|loyer|rent|moins|under|max|avec|for|daily|hebdo)\b", candidate)[0]
    candidate = candidate.strip(" -")
    return candidate or None


def title_case_city(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())

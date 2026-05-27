from __future__ import annotations

from typing import Any

LISTING_RANKER_PROMPT = """Tu evalues une annonce immobiliere pour une recherche locative.
Retourne uniquement du JSON valide.
N'invente jamais une donnee manquante.
Tu ne modifies jamais le score deterministe fourni par l'application.
Si les charges, la disponibilite, l'adresse precise ou le contact ne sont pas explicitement presents, ajoute un drapeau de risque.
Chaque raison doit etre justifiee par une donnee presente dans l'annonce, les criteres, le dossier ou le score deterministe.
Le score final doit etre compris entre 0 et 100.
"""

LISTING_RANKER_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fit_score", "fit_level", "reasons", "risk_flags", "recommendation"],
    "properties": {
        "fit_score": {"type": "number", "minimum": 0, "maximum": 100},
        "fit_level": {"type": "string", "enum": ["strong", "medium", "low"]},
        "reasons": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "risk_flags": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommendation": {
            "type": "string",
            "enum": ["recommend", "review", "reject"],
        },
    },
}

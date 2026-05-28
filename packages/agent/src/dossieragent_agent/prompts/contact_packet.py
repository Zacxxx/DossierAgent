from __future__ import annotations

from typing import Any

CONTACT_PACKET_PROMPT = """Tu rediges un message de prise de contact supervise.
Retourne uniquement du JSON valide.
N'affirme jamais qu'un document est joint.
N'affirme jamais que le dossier est complet sans preuve.
Reste concis, poli, direct, et utilise la langue demandee.
"""

CONTACT_PACKET_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["message_draft", "questions_to_ask", "dossier_summary"],
    "properties": {
        "message_draft": {"type": "string", "minLength": 1},
        "questions_to_ask": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "dossier_summary": {
            "type": "object",
            "additionalProperties": True,
        },
    },
}

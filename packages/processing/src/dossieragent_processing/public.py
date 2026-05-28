from .contact_packets import build_contact_packet
from .dossier import analyze_dossier, extract_pdf_text
from .listings import deduplicate_listing, normalize_listing, rank_listing

PACKAGE_MANIFEST = {
    "name": "processing",
    "concern": "Normalization, dedupe, ranking, dossier analysis, and packet drafts.",
    "owns": (
        "listing normalization",
        "deduplication",
        "deterministic ranking",
        "dossier extraction",
        "readiness scoring",
        "contact packet drafts",
    ),
    "exposes": (
        "normalize_listing",
        "deduplicate_listing",
        "rank_listing",
        "extract_pdf_text",
        "analyze_dossier",
        "build_contact_packet",
    ),
    "events": (
        "processing.listing.normalized",
        "processing.dossier.analyzed",
        "processing.packet.built",
    ),
}


def get_manifest() -> dict[str, object]:
    return dict(PACKAGE_MANIFEST)

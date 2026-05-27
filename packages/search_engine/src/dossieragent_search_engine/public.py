from .indices import ensure_indices, load_mapping, verify_index_mapping
from .queries import build_listing_search_query

PACKAGE_MANIFEST = {
    "name": "search_engine",
    "concern": "Elasticsearch mappings, indexing, and hybrid search.",
    "owns": (
        "elastic mappings",
        "index bootstrap",
        "lexical search",
        "vector search",
        "hybrid retrieval",
    ),
    "exposes": (
        "ensure_indices",
        "index_listing",
        "index_document",
        "search_listings",
    ),
    "events": (
        "search.index.ready",
        "search.document.indexed",
    ),
}


def get_manifest() -> dict[str, object]:
    return dict(PACKAGE_MANIFEST)

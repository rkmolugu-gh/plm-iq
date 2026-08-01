"""BM25 keyword search module.

Provides pure BM25 (Best Match 25) keyword search against Elasticsearch indices.
BM25 is a bag-of-words retrieval function that ranks documents based on the query
terms appearing in each document, using term frequency and inverse document frequency.

This module is used by the hybrid search module (bm25vectorrrf.py) and can also
be used directly for pure keyword-based search.
"""

import logging
import time
from typing import Optional

from .config import ALL_INDICES, SEARCH_DEFAULT_SIZE, SEARCH_MAX_SIZE
from .es_client import get_es

logger = logging.getLogger(__name__)


def build_bm25_body(query: str) -> dict:
    """Build a pure BM25 keyword search body for Elasticsearch.

    Args:
        query: The user's search query string.

    Returns:
        An Elasticsearch query body dict for BM25 search.
    """
    return {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["content^2", "*"],
                "type": "best_fields",
            }
        }
    }


def bm25_search(
    query: str,
    entity_type: Optional[str] = None,
    page: int = 1,
    size: int = SEARCH_DEFAULT_SIZE,
) -> dict:
    """Run pure BM25 keyword search across PLM indices.

    This function performs keyword-based search only (no vector/semantic search).
    It is faster than hybrid search and works well for exact match queries.

    Args:
        query:        The user's search query string.
        entity_type:  Optional filter — e.g. "Parts", "ECO", "Documents".
        page:         Page number (1-indexed) for pagination.
        size:         Results per page (capped at SEARCH_MAX_SIZE).

    Returns:
        dict with keys:
            results:  list of raw ES hits (not yet formatted)
            total:    total match count
            page:     current page
            pages:    total pages
            timing:   dict with timing breakdown
    """
    t_start = time.time()

    # Fail fast if ES is not reachable
    try:
        es = get_es()
    except ConnectionError as e:
        logger.warning(f"Elasticsearch not reachable: {e}")
        return {
            "results": [],
            "total": 0,
            "page": page,
            "pages": 0,
            "es_error": str(e),
            "timing": {"total_seconds": round(time.time() - t_start, 3)},
        }

    size = min(size, SEARCH_MAX_SIZE)
    from_idx = (page - 1) * size

    # Determine which indices to search
    target_indices = _resolve_indices(entity_type)
    logger.info(f"BM25 search query='{query}' entity={entity_type} indices={target_indices}")

    # Run BM25 search against each target index
    all_results = []
    true_total = 0
    t_search_start = time.time()

    body = build_bm25_body(query)

    for idx_name in target_indices:
        try:
            resp = es.search(
                index=idx_name, body=body, size=size * 2,
                track_total_hits=True, _source_excludes=["content_vector"],
            )
            hits = resp["hits"]["hits"]
            logger.debug(f"  {idx_name}: {len(hits)} hits")
            all_results.extend(hits)
            true_total += _extract_total(resp)
        except Exception as e:
            logger.warning(f"BM25 search failed on {idx_name}: {e}")

    t_search_elapsed = time.time() - t_search_start

    # Sort by score descending and paginate
    all_results.sort(key=lambda h: h.get("_score", 0), reverse=True)
    total = true_total
    paginated = all_results[from_idx:from_idx + size]

    t_elapsed = time.time() - t_start
    logger.info(f"BM25 search complete: {total} total results, {len(paginated)} returned in {t_elapsed:.3f}s")

    return {
        "results": paginated,
        "total": total,
        "page": page,
        "pages": max(1, (total + size - 1) // size),
        "timing": {
            "total_seconds": round(t_elapsed, 3),
            "search_seconds": round(t_search_elapsed, 3),
        },
    }


def _extract_total(resp: dict) -> int:
    """Return the accurate match count from an ES response (track_total_hits)."""
    total = resp.get("hits", {}).get("total", {})
    if isinstance(total, dict):
        return int(total.get("value", 0))
    return int(total or 0)


def _resolve_indices(entity_type: Optional[str]) -> list[str]:
    """Map a user-facing entity label to internal index names.

    This is a local copy to avoid circular imports. The canonical version
    lives in search.py.
    """
    from .search import ENTITY_LABELS
    if not entity_type or entity_type == "All":
        return ALL_INDICES
    entity_upper = entity_type.upper()
    for idx, label in ENTITY_LABELS.items():
        if label.upper() == entity_upper:
            return [idx]
    # Try matching against index name or label directly
    for idx, label in ENTITY_LABELS.items():
        if entity_type.lower() in idx.lower() or entity_type.lower() in label.lower():
            return [idx]
    return ALL_INDICES

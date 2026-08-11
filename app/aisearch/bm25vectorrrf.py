"""Hybrid search module — BM25 + vector (kNN) + RRF fusion.

Provides hybrid search that combines:
1. BM25 keyword search (lexical matching)
2. kNN vector search (semantic matching via embeddings)
3. RRF (Reciprocal Rank Fusion) to merge and re-rank results

This module is used for RAG mode and Hybrid mode searches, where both keyword
and semantic relevance are important.
"""

import logging
import time
from typing import Optional

from .config import ALL_INDICES, SEARCH_DEFAULT_SIZE, SEARCH_MAX_SIZE
from .es_client import get_es
from .filter_gateway import gate_query, gate_results, require_tenant_key, TenantFilterDenied

logger = logging.getLogger(__name__)


def build_knn_body(query_vector: list[float], tenant_key: Optional[str] = None) -> dict:
    """Build a pure kNN vector search body for Elasticsearch.

    Args:
        query_vector: The query embedding vector.
        tenant_key: The server-derived tenant key (deny-by-default if missing).

    Returns:
        An Elasticsearch query body dict for kNN search, with the mandatory
        tenant filter injected by the filter gateway.

    Raises:
        TenantFilterDenied: if ``tenant_key`` is missing.
    """
    body = {
        "query": {
            "bool": {
                "must": [{
                    "knn": {
                        "field": "content_vector",
                        "query_vector": query_vector,
                        "k": 20,
                        "num_candidates": 50,
                    }
                }]
            }
        }
    }
    # The filter gateway is the single place that injects the tenant term.
    return gate_query(body, tenant_key, caller="hybrid.build_knn_body")


def rrf_fusion(
    bm25_hits: list[dict],
    knn_hits: list[dict],
    rank_constant: int = 60,
) -> list[dict]:
    """Fuse two ranked result lists using Reciprocal Rank Fusion (RRF).

    The RRF formula: score = 1 / (rank_constant + rank)
    where rank is the 0-based position of the document in each result list.
    Documents appearing in both lists receive a higher combined score.

    Args:
        bm25_hits:     List of ES hit dicts from BM25 search.
        knn_hits:      List of ES hit dicts from kNN search.
        rank_constant: The RRF rank constant k (default 60, matching ES default).

    Returns:
        List of hit dicts with updated _score set to the fused RRF score,
        sorted by score descending.
    """
    scores: dict[str, float] = {}

    for rank, hit in enumerate(bm25_hits):
        doc_id = hit["_id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rank_constant + rank + 1)

    for rank, hit in enumerate(knn_hits):
        doc_id = hit["_id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rank_constant + rank + 1)
        # If this doc wasn't in BM25 results, carry over its source
        if doc_id not in {h["_id"] for h in bm25_hits}:
            bm25_hits.append(hit)

    # Build fused result list, preserving the richer hit dict (prefer knn source)
    knn_by_id = {h["_id"]: h for h in knn_hits}
    bm25_by_id = {h["_id"]: h for h in bm25_hits}

    fused = []
    seen = set()
    for doc_id in sorted(scores, key=scores.get, reverse=True):  # type: ignore[arg-type]
        # Prefer the kNN hit dict (has _source with vector), fall back to BM25
        hit = knn_by_id.get(doc_id, bm25_by_id.get(doc_id))
        if hit and doc_id not in seen:
            hit["_score"] = round(scores[doc_id], 4)
            fused.append(hit)
            seen.add(doc_id)

    return fused


def hybrid_search(
    query: str,
    entity_type: Optional[str] = None,
    page: int = 1,
    size: int = SEARCH_DEFAULT_SIZE,
    search_mode: str = "rag",
    tenant_key: Optional[str] = None,
) -> dict:
    """Run hybrid BM25 + vector search across PLM indices.

    This is the central hybrid search function. It:
    1. Embeds the query via the LLM API (Python llm_client.embed)
    2. Runs BM25 keyword search AND kNN vector search in parallel
    3. Fuses results via RRF (Reciprocal Rank Fusion)
    4. Optionally filters by entity type and tenant_key

    Args:
        query:        The user's search query string.
        entity_type:  Optional filter — e.g. "Parts", "ECO", "Documents".
        page:         Page number (1-indexed) for pagination.
        size:         Results per page (capped at SEARCH_MAX_SIZE).
        search_mode:  "rag" for hybrid BM25+vector (default).
        tenant_key:   Optional tenant key to filter results (multi-tenant isolation).

    Returns:
        dict with keys:
            results:  list of raw ES hits (not yet formatted)
            total:    total match count across all searched indices
            page:     current page
            pages:    total pages
            query:    original query
            entity_type: applied filter
            search_mode: which mode was used
            timing:   dict with timing breakdown
    """
    t_start = time.time()

    # Deny-by-default: no tenant key => no query (logged by the gateway).
    try:
        require_tenant_key(tenant_key, caller="hybrid.hybrid_search")
    except TenantFilterDenied:
        return _denied_result(query, entity_type, page, size, search_mode, t_start)

    # Fail fast if ES is not reachable — return an error result
    try:
        es = get_es()
    except ConnectionError as e:
        logger.warning(f"Elasticsearch not reachable: {e}")
        return {
            "results": [],
            "total": 0,
            "page": page,
            "pages": 0,
            "query": query,
            "entity_type": entity_type or "",
            "search_mode": search_mode,
            "es_error": str(e),
            "timing": {"total_seconds": round(time.time() - t_start, 3)},
        }

    size = min(size, SEARCH_MAX_SIZE)
    from_idx = (page - 1) * size

    # Determine which indices to search
    target_indices = _resolve_indices(entity_type)
    logger.info(f"Hybrid search query='{query}' entity={entity_type} tenant_key={tenant_key} indices={target_indices}")

    # Build the query embedding (for vector search)
    query_vector = None
    t_embed_start = time.time()
    try:
        query_vector = _embed_query(query)
    except Exception as e:
        t_embed_elapsed = time.time() - t_embed_start
        logger.warning(f"Query embedding failed: {e}")
        return {
            "results": [],
            "total": 0,
            "page": page,
            "pages": 0,
            "query": query,
            "entity_type": entity_type or "",
            "search_mode": search_mode,
            "embed_error": str(e),
            "timing": {
                "total_seconds": round(time.time() - t_start, 3),
                "embed_seconds": round(t_embed_elapsed, 3),
            },
        }
    t_embed_elapsed = time.time() - t_embed_start
    logger.debug(f"Query embedding took {t_embed_elapsed:.3f}s")

    # Run search against each target index
    all_results = []
    true_total = 0
    t_search_start = time.time()

    from .bm25 import build_bm25_body

    for idx_name in target_indices:
        try:
            # Run BM25 and kNN as separate queries, then fuse with RRF in Python
            bm25_body = build_bm25_body(query, tenant_key=tenant_key)
            knn_body = build_knn_body(query_vector, tenant_key=tenant_key)

            bm25_resp = es.search(
                index=idx_name, body=bm25_body, size=size * 2,
                track_total_hits=True, _source_excludes=["content_vector"],
            )
            knn_resp = es.search(
                index=idx_name, body=knn_body, size=size * 2,
                track_total_hits=True, _source_excludes=["content_vector"],
            )

            bm25_hits = bm25_resp["hits"]["hits"]
            knn_hits = knn_resp["hits"]["hits"]
            logger.debug(f"  {idx_name}: BM25={len(bm25_hits)} hits, kNN={len(knn_hits)} hits")

            fused = rrf_fusion(bm25_hits, knn_hits)
            for hit in fused:
                all_results.append(hit)

            # True match count: use the richer of BM25/kNN totals,
            # because fusion can surface kNN-only hits that BM25 missed.
            bm25_total = _extract_total(bm25_resp)
            knn_total = _extract_total(knn_resp)
            true_total += max(bm25_total, knn_total)
        except Exception as e:
            logger.warning(f"Hybrid search failed on {idx_name}: {e}")

    t_search_elapsed = time.time() - t_search_start

    # Defense-in-depth: keep only fused hits belonging to the caller's tenant.
    all_results = gate_results(all_results, tenant_key, caller="hybrid.hybrid_search")

    # Sort by score descending and paginate
    all_results.sort(key=lambda r: r.get("_score", 0), reverse=True)
    total = min(len(all_results), true_total)
    paginated = all_results[from_idx:from_idx + size]

    t_elapsed = time.time() - t_start
    logger.info(f"Hybrid search complete: {total} total results, {len(paginated)} returned in {t_elapsed:.3f}s")

    return {
        "results": paginated,
        "total": total,
        "page": page,
        "pages": max(1, (total + size - 1) // size),
        "query": query,
        "entity_type": entity_type or "",
        "search_mode": search_mode,
        "timing": {
            "total_seconds": round(t_elapsed, 3),
            "embed_seconds": round(t_embed_elapsed, 3),
            "search_seconds": round(t_search_elapsed, 3),
        },
    }


def _denied_result(query: str, entity_type: Optional[str], page: int, size: int, search_mode: str, t_start: float) -> dict:
    """Return an empty result for deny-by-default when no tenant key is present.

    Flags ``denied`` so the caller can distinguish a tenancy denial from a
    genuine "no results" without revealing anything about other tenants.
    """
    return {
        "results": [],
        "total": 0,
        "page": page,
        "pages": 0,
        "query": query,
        "entity_type": entity_type or "",
        "search_mode": search_mode,
        "denied": True,
        "timing": {"total_seconds": round(time.time() - t_start, 3)},
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


def _embed_query(query: str) -> list[float]:
    """Generate query embedding using Python (llm_client).

    Calls the LLM API directly via llm_client.embed() instead of using
    an ES inference pipeline (which requires a Platinum ES license).
    """
    from .llm_client import embed as api_embed
    return api_embed(query)

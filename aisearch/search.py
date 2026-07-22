"""Hybrid search engine — BM25 + vector + RRF across all PLM indices.

Summary:
    Provides the core search function that:
    1. Embeds the query via the LLM API (Python llm_client.embed)
    2. Runs BM25 keyword search AND kNN vector search in parallel
    3. Fuses results via RRF (Reciprocal Rank Fusion)
    4. Optionally filters by entity type

    Logs detailed search telemetry for debugging and observability.

    Error handling:
        hybrid_search() catches ConnectionError from get_es() and returns
        an error result dict with 'es_error' set, so callers can display
        a friendly "Elasticsearch not reachable" message.
"""

import logging
import time
from typing import Optional

from aisearch.config import (
    ALL_INDICES, SEARCH_DEFAULT_SIZE, SEARCH_MAX_SIZE,
    INDEX_PARTS, INDEX_BOM, INDEX_COSTING, INDEX_ECO,
    INDEX_AML, INDEX_AVL, INDEX_CAD, INDEX_DOCS,
)
from aisearch.es_client import get_es

logger = logging.getLogger(__name__)

# Entity type labels for display and filtering
ENTITY_LABELS = {
    INDEX_PARTS: "Parts",
    INDEX_BOM: "BOM",
    INDEX_COSTING: "Costing",
    INDEX_ECO: "ECO",
    INDEX_AML: "AML",
    INDEX_AVL: "AVL",
    INDEX_CAD: "CAD",
    INDEX_DOCS: "Documents",
}

# Which field to display as the "title" in search results
ENTITY_TITLE_FIELD = {
    INDEX_PARTS: "part_number",
    INDEX_BOM: "part_number",
    INDEX_COSTING: "part_number",
    INDEX_ECO: "eco_number",
    INDEX_AML: "part_number",
    INDEX_AVL: "part_number",
    INDEX_CAD: "cad_file_name",
    INDEX_DOCS: "filename",
}

# Fields to include in snippet text
ENTITY_SNIPPET_FIELDS = {
    INDEX_PARTS: ["part_name", "material", "status"],
    INDEX_BOM: ["part_name", "parent_assembly", "bom_type"],
    INDEX_COSTING: ["part_name", "cost_type", "unit_cost"],
    INDEX_ECO: ["eco_title", "eco_description", "change_detail"],
    INDEX_AML: ["manufacturer_name", "manufacturer_part_number"],
    INDEX_AVL: ["vendor_name", "vendor_part_number"],
    INDEX_CAD: ["cad_file_format", "cad_system", "drawing_number"],
    INDEX_DOCS: ["page_num", "part_number"],
}


def hybrid_search(
    query: str,
    entity_type: Optional[str] = None,
    page: int = 1,
    size: int = SEARCH_DEFAULT_SIZE,
    search_mode: str = "bm25",
) -> dict:
    """Run hybrid BM25 + vector search across PLM indices.

    This is the central search function. It:
    1. Identifies which indices to search (all or filtered by entity_type)
    2. Embeds the query via Python (llm_client) for vector search mode
    3. Runs BM25 + kNN queries with RRF fusion
    4. Returns structured results with scores, snippets, and metadata

    Args:
        query:        The user's search query string.
        entity_type:  Optional filter — e.g. "Parts", "ECO", "Documents".
        page:         Page number (1-indexed) for pagination.
        size:         Results per page (capped at SEARCH_MAX_SIZE).
        search_mode:  "bm25" for pure keyword, "rag" for hybrid BM25+vector.

    Returns:
        dict with keys:
            results:  list of {index, id, score, title, snippet, fields, entity_label}
            total:    total match count across all searched indices
            page:     current page
            pages:    total pages
            query:    original query
            entity_type: applied filter
            search_mode: which mode was used
            timing:   dict with timing breakdown
    """
    t_start = time.time()

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
    logger.info(f"Search mode={search_mode} query='{query}' entity={entity_type} indices={target_indices}")

    # Build the query embedding (for vector/rag mode)
    query_vector = None
    t_embed_start = time.time()
    if search_mode == "rag":
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

    for idx_name in target_indices:
        try:
            if search_mode == "rag" and query_vector:
                # Run BM25 and kNN as separate queries, then fuse with RRF in Python
                bm25_body = _build_bm25_body(query)
                knn_body = _build_knn_body(query_vector)

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

                fused = _rrf_fusion(bm25_hits, knn_hits)
                for hit in fused:
                    entry = _format_hit(hit, idx_name, query)
                    all_results.append(entry)
            else:
                # Pure BM25 keyword search
                body = _build_bm25_body(query)
                resp = es.search(
                    index=idx_name, body=body, size=size * 2,
                    track_total_hits=True, _source_excludes=["content_vector"],
                )
                hits = resp["hits"]["hits"]
                logger.debug(f"  {idx_name}: {len(hits)} hits")
                for hit in hits:
                    entry = _format_hit(hit, idx_name, query)
                    all_results.append(entry)

            # True match count: sum of accurate total_hits across all indices.
            true_total += _extract_total(resp if search_mode != "rag" else bm25_resp)
        except Exception as e:
            logger.warning(f"Search failed on {idx_name}: {e}")

    t_search_elapsed = time.time() - t_search_start

    # Sort by score descending and paginate
    all_results.sort(key=lambda r: r["score"], reverse=True)
    total = true_total
    paginated = all_results[from_idx:from_idx + size]

    t_elapsed = time.time() - t_start
    logger.info(f"Search complete: {total} total results, {len(paginated)} returned in {t_elapsed:.3f}s")

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


def _extract_total(resp: dict) -> int:
    """Return the accurate match count from an ES response (track_total_hits)."""
    total = resp.get("hits", {}).get("total", {})
    if isinstance(total, dict):
        return int(total.get("value", 0))
    return int(total or 0)


def _resolve_indices(entity_type: Optional[str]) -> list[str]:
    """Map a user-facing entity label to internal index names."""
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
    from aisearch.llm_client import embed as api_embed
    return api_embed(query)


def _build_bm25_body(query: str) -> dict:
    """Build a pure BM25 keyword search body."""
    return {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["content^2", "*"],
                "type": "best_fields",
            }
        }
    }


def _build_knn_body(query_vector: list[float]) -> dict:
    """Build a pure kNN vector search body."""
    return {
        "query": {
            "knn": {
                "field": "content_vector",
                "query_vector": query_vector,
                "k": 20,
                "num_candidates": 50,
            }
        }
    }


def _rrf_fusion(bm25_hits: list[dict], knn_hits: list[dict], rank_constant: int = 60) -> list[dict]:
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


def _format_hit(hit: dict, index_name: str, query: str) -> dict:
    """Format a raw ES hit into a user-friendly search result dict."""
    source = hit.get("_source", {})
    # Never return the embedding vector to clients (bandwidth + privacy).
    source.pop("content_vector", None)
    score = hit.get("_score", 0) or hit.get("_rank", 0)

    title_field = ENTITY_TITLE_FIELD.get(index_name, "content")
    title = str(source.get(title_field, source.get("content", "")))[:120]

    # Build snippet from display fields
    snippet_parts = []
    for field in ENTITY_SNIPPET_FIELDS.get(index_name, []):
        val = source.get(field)
        if val is not None:
            snippet_parts.append(f"{field}: {val}")
    snippet = " | ".join(snippet_parts)
    if not snippet:
        snippet = str(source.get("content", ""))[:200]

    return {
        "index": index_name,
        "id": hit.get("_id", ""),
        "score": round(score, 4),
        "title": title,
        "snippet": snippet,
        "fields": source,
        "entity_label": ENTITY_LABELS.get(index_name, index_name),
    }

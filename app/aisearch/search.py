"""Main search entry point — orchestrates BM25, hybrid, and RAG searches.

This module provides the main public API for search functionality:
- search(): Main entry point that routes to BM25 or hybrid search based on mode
- Result formatting and URL generation for business object navigation

For implementation details:
- BM25 search: See bm25.py
- Hybrid (BM25 + vector) search: See bm25vectorrrf.py
- RAG answer generation: See ragai.py
"""

import logging
from typing import Optional

from .config import (
    ALL_INDICES, SEARCH_DEFAULT_SIZE, SEARCH_MAX_SIZE,
    INDEX_PARTS, INDEX_BOM, INDEX_COSTING, INDEX_ECO,
    INDEX_AML, INDEX_AVL, INDEX_CAD, INDEX_DOCS,
)

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


def search(
    query: str,
    mode: str = "bm25",
    entity_type: Optional[str] = None,
    page: int = 1,
    size: int = SEARCH_DEFAULT_SIZE,
    tenant_id: Optional[int] = None,
) -> dict:
    """Main search entry point — routes to BM25 or hybrid search based on mode.

    Args:
        query:        The user's search query string.
        mode:         Search mode: "bm25" for keyword, "rag" or "hybrid" for hybrid.
        entity_type:  Optional filter — e.g. "Parts", "ECO", "Documents".
        page:         Page number (1-indexed) for pagination.
        size:         Results per page (capped at SEARCH_MAX_SIZE).
        tenant_id:    Optional tenant ID to filter results (multi-tenant isolation).

    Returns:
        dict with keys:
            results:  list of formatted results with {index, id, score, title, snippet, url, ...}
            total:    total match count
            page:     current page
            pages:    total pages
            query:    original query
            entity_type: applied filter
            search_mode: which mode was used
            timing:   dict with timing breakdown
    """
    if mode == "bm25":
        from .bm25 import bm25_search
        raw_result = bm25_search(query, entity_type, page, size, tenant_id=tenant_id)
    else:  # "rag" or "hybrid" mode
        from .bm25vectorrrf import hybrid_search
        raw_result = hybrid_search(query, entity_type, page, size, search_mode=mode, tenant_id=tenant_id)

    # Format the raw ES hits into user-friendly result dicts
    formatted_results = []
    for hit in raw_result.get("results", []):
        # Determine index name from the hit (it should be in the hit metadata)
        index_name = hit.get("_index", "")
        formatted = _format_hit(hit, index_name, query)
        formatted_results.append(formatted)

    # Build the final result dict
    return {
        "results": formatted_results,
        "total": raw_result.get("total", 0),
        "page": raw_result.get("page", page),
        "pages": raw_result.get("pages", 1),
        "query": query,
        "entity_type": entity_type or "",
        "search_mode": mode,
        "timing": raw_result.get("timing", {}),
        "es_error": raw_result.get("es_error"),
        "embed_error": raw_result.get("embed_error"),
    }


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

    # Generate URL for navigation to the business object detail page
    url = _generate_result_url(index_name, hit, source)

    return {
        "index": index_name,
        "id": hit.get("_id", ""),
        "score": round(score, 4),
        "title": title,
        "snippet": snippet,
        "fields": source,
        "entity_label": ENTITY_LABELS.get(index_name, index_name),
        "url": url,
    }


def _generate_result_url(index_name: str, hit: dict, source: dict) -> str:
    """Generate a URL to navigate to the business object detail page.

    Args:
        index_name: The Elasticsearch index name (e.g., 'plm_parts').
        hit: The raw ES hit dict (contains '_id').
        source: The document '_source' fields.

    Returns:
        A URL path string (e.g., '/parts/P-001') or empty string if no URL applies.
    """
    # Use ES document ID (assumed to be the DB id for CAD, Documents, etc.)
    doc_id = hit.get("_id", "")

    if index_name == "plm_parts":
        part_number = source.get("part_number", "")
        return f"/parts/{part_number}" if part_number else ""

    elif index_name == "plm_bom":
        part_number = source.get("part_number", "")
        parent_assembly = source.get("parent_assembly", "")
        # Link to BOM tree view for the assembly if available, otherwise part detail
        if parent_assembly:
            return f"/bom/tree/{parent_assembly}"
        return f"/parts/{part_number}" if part_number else ""

    elif index_name == "plm_cad":
        # CAD files use integer DB id
        return f"/cad/{doc_id}" if doc_id else ""

    elif index_name == "plm_docs":
        # Documents use integer DB id
        return f"/documents/{doc_id}" if doc_id else ""

    elif index_name == "plm_eco":
        eco_number = source.get("eco_number", "")
        return f"/eco?q={eco_number}" if eco_number else ""

    elif index_name in ("plm_aml", "plm_avl"):
        # AML/AVL entries link to the part detail page
        part_number = source.get("part_number", "")
        return f"/parts/{part_number}" if part_number else ""

    elif index_name == "plm_costing":
        part_number = source.get("part_number", "")
        return f"/parts/{part_number}" if part_number else ""

    return ""


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

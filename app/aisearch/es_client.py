"""Elasticsearch client — connection, index creation, and pipeline setup.

Summary:
    Provides get_es() for a singleton ES connection, and helpers to:
    - Create indices with proper mappings (text + dense_vector + keyword)
    - Set up inference pipelines that call the LLM API for auto-embedding
    - Delete/recreate indices for rebuilds
"""

import logging
from typing import Optional
from elasticsearch import Elasticsearch

from .config import (
    ES_HOST, ES_USER, ES_PASSWORD,
    EMBEDDING_DIMENSIONS,
    INDEX_PARTS, INDEX_BOM, INDEX_COSTING, INDEX_ECO,
    INDEX_AML, INDEX_AVL, INDEX_CAD, INDEX_DOCS,
)

logger = logging.getLogger(__name__)

_es: Optional[Elasticsearch] = None


def get_es() -> Elasticsearch:
    """Return a singleton Elasticsearch client connection.

    Uses basic auth if ES_USER is set, otherwise connects anonymously.

    Note: ping() returns False on 401 (auth required), so we use info()
    instead and treat AuthenticationException as a valid connection that
    simply needs credentials configured.
    """
    global _es
    if _es is not None:
        try:
            if _es.ping():
                return _es
        except Exception:
            pass  # Need to reconnect below

    kwargs = {"hosts": [ES_HOST]}
    if ES_USER:
        kwargs["basic_auth"] = (ES_USER, ES_PASSWORD)

    # Self-signed certs from ES auto-configuration
    kwargs["verify_certs"] = False
    kwargs["ssl_show_warn"] = False

    # Fail fast when ES is not running — don't let the user wait
    kwargs["request_timeout"] = 3
    kwargs["connections_per_node"] = 1

    _es = Elasticsearch(**kwargs)

    # info() will raise AuthenticationException (401) if ES needs auth.
    # That's fine — it means ES is running. Only transport failures
    # (connection refused, DNS, SSL) should raise ConnectionError.
    try:
        _es.info()
        logger.info(f"Connected to Elasticsearch at {ES_HOST}")
    except Exception as e:
        status = getattr(e, "status_code", None)
        if status == 401:
            logger.info(f"Connected to Elasticsearch at {ES_HOST} (authentication required)")
        else:
            raise ConnectionError(f"Cannot connect to Elasticsearch at {ES_HOST}: {e}")

    return _es


def close_es():
    """Close the ES connection (used during shutdown)."""
    global _es
    if _es:
        _es.close()
        _es = None


# ── Index Mappings ─────────────────────────────────────────────
# Each index has:
#   - content (text):      Combined searchable text for BM25
#   - content_vector:       Populated by Python (llm_client.embed()) before indexing
#   - entity_type (keyword): Filters for entity-specific searches
#   - entity-specific fields for display

BASE_MAPPINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "content": {"type": "text"},
            "content_vector": {
                "type": "dense_vector",
                "dims": EMBEDDING_DIMENSIONS,
                "index": True,
                "similarity": "cosine",
            },
            "entity_type": {"type": "keyword"},
        },
    },
}

# Per-index field definitions (merged into BASE_MAPPINGS)
INDEX_FIELDS = {
    INDEX_PARTS: {
        "part_number": {"type": "keyword"},
        "part_revision": {"type": "keyword"},
        "part_name": {"type": "text"},
        "material": {"type": "text"},
        "uom": {"type": "keyword"},
        "qty": {"type": "integer"},
        "status": {"type": "keyword"},
        "spec_file": {"type": "text"},
    },
    INDEX_BOM: {
        "part_number": {"type": "keyword"},
        "part_revision": {"type": "keyword"},
        "part_name": {"type": "text"},
        "qty": {"type": "integer"},
        "uom": {"type": "keyword"},
        "parent_assembly": {"type": "keyword"},
        "bom_type": {"type": "keyword"},
        "level": {"type": "integer"},
    },
    INDEX_COSTING: {
        "part_number": {"type": "keyword"},
        "part_name": {"type": "text"},
        "qty": {"type": "integer"},
        "uom": {"type": "keyword"},
        "cost_type": {"type": "keyword"},
        "material_cost": {"type": "float"},
        "labor_cost": {"type": "float"},
        "overhead_cost": {"type": "float"},
        "unit_cost": {"type": "float"},
        "rolled_total": {"type": "float"},
    },
    INDEX_ECO: {
        "eco_number": {"type": "keyword"},
        "eco_title": {"type": "text"},
        "eco_description": {"type": "text"},
        "eco_status": {"type": "keyword"},
        "part_number": {"type": "keyword"},
        "change_type": {"type": "keyword"},
        "change_detail": {"type": "text"},
        "current_revision": {"type": "keyword"},
        "new_revision": {"type": "keyword"},
    },
    INDEX_AML: {
        "part_number": {"type": "keyword"},
        "manufacturer_name": {"type": "text"},
        "manufacturer_part_number": {"type": "text"},
        "preferred_flag": {"type": "keyword"},
        "lead_time_days": {"type": "integer"},
        "unit_cost": {"type": "float"},
        "quality_rating": {"type": "keyword"},
    },
    INDEX_AVL: {
        "part_number": {"type": "keyword"},
        "vendor_name": {"type": "text"},
        "vendor_part_number": {"type": "text"},
        "preferred_flag": {"type": "keyword"},
        "unit_price": {"type": "float"},
        "min_order_qty": {"type": "integer"},
        "lead_time_days": {"type": "integer"},
        "iso_certified": {"type": "keyword"},
    },
    INDEX_CAD: {
        "part_number": {"type": "keyword"},
        "part_revision": {"type": "keyword"},
        "cad_file_name": {"type": "text"},
        "cad_file_format": {"type": "keyword"},
        "cad_system": {"type": "text"},
        "file_reference_type": {"type": "keyword"},
        "file_size_bytes": {"type": "long"},
        "drawing_number": {"type": "keyword"},
    },
    INDEX_DOCS: {
        "filename": {"type": "keyword"},
        "page_num": {"type": "integer"},
        "chunk_index": {"type": "integer"},
        "total_chunks": {"type": "integer"},
        "chunk_text": {"type": "text"},
        "part_number": {"type": "keyword"},
    },
}


def _build_mappings(index_name: str) -> dict:
    """Merge BASE_MAPPINGS with index-specific field definitions."""
    import copy
    mappings = copy.deepcopy(BASE_MAPPINGS)
    extra_fields = INDEX_FIELDS.get(index_name, {})
    mappings["mappings"]["properties"].update(extra_fields)
    return mappings


def create_index(index_name: str, force_delete: bool = False):
    """Create an ES index with proper mappings.

    Args:
        index_name: Name of the index to create.
        force_delete: If True, delete existing index first.
    """
    es = get_es()

    if force_delete and es.indices.exists(index=index_name):
        logger.info(f"Deleting existing index: {index_name}")
        es.indices.delete(index=index_name)

    if not es.indices.exists(index=index_name):
        mappings = _build_mappings(index_name)
        es.indices.create(index=index_name, body=mappings)
        logger.info(f"Created index: {index_name} with {len(mappings['mappings']['properties'])} fields")
    else:
        logger.info(f"Index already exists: {index_name}")


def setup_inference_pipeline():
    """No-op — embeddings are generated in Python (llm_client.embed()) during indexing.

    Previously this created an ES inference endpoint + ingest pipeline,
    but that requires a Platinum ES license. Embeddings are now generated
    by the index builders before pushing documents to ES.
    """
    logger.info("Embeddings generated in Python (no ES inference pipeline needed)")

"""Provision search indices with correct mappings (idempotent).

Summary:
    Ensures every PLM index exists with the right mappings on the configured
    SearchBackend before documents are published. Safe to run repeatedly:
    existing indices are left untouched unless --force is passed.

    Embeddings are generated in Python (llm_client.embed) during staging, so no
    ES inference pipeline / ingest pipeline is created here (that required a
    Platinum license). setup_inference_pipeline() remains a documented no-op.

    Usage:
        python -m db.indexing.setup_es [--force]

    Flags:
        --force   Delete and recreate each index (drops existing data).
"""

import sys
import logging

from aisearch.config import validate
from aisearch.backend import get_backend
from aisearch.config import (
    INDEX_PARTS, INDEX_BOM, INDEX_COSTING, INDEX_ECO,
    INDEX_AML, INDEX_AVL, INDEX_CAD, INDEX_DOCS,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("setup_es")

ALL_INDICES = [
    INDEX_PARTS, INDEX_BOM, INDEX_COSTING, INDEX_ECO,
    INDEX_AML, INDEX_AVL, INDEX_CAD, INDEX_DOCS,
]


def main():
    force = "--force" in sys.argv

    for w in validate():
        logger.warning(w)

    try:
        backend = get_backend()
    except Exception as e:
        logger.error(f"Cannot initialize search backend: {e}")
        sys.exit(1)

    if not backend.health():
        logger.error("Search backend is not reachable; cannot create indices.")
        sys.exit(1)

    logger.info(f"Provisioning {len(ALL_INDICES)} indices (force={force})")
    for index_name in ALL_INDICES:
        try:
            backend.ensure_index(index_name, force_recreate=force)
        except Exception as e:
            logger.error(f"  Failed to provision {index_name}: {e}")
            sys.exit(1)

    logger.info("All indices provisioned.")


if __name__ == "__main__":
    main()

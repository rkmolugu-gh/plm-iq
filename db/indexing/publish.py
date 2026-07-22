"""Publish staged documents to the configured search backend.

Summary:
    Reads backend-neutral JSONL documents produced by the builders
    (db/indexing/build_*.py) and pushes them to the active SearchBackend in
    batches. This is the only module that talks to the search engine, so the
    backend can be swapped (Elasticsearch, OpenSearch, ...) without touching any
    builder or staging code.

    Usage:
        python -m db.indexing.publish [--force] [--index NAME]

    Flags:
        --force     Recreate each target index before publishing (full rebuild).
        --index     Publish only the named index (e.g. plm_parts, plm_docs).
"""

import sys
import logging

from aisearch.config import validate
from aisearch.backend import get_backend
from db.indexing.staging import StagingStore
from aisearch.config import (
    INDEX_PARTS, INDEX_BOM, INDEX_COSTING, INDEX_ECO,
    INDEX_AML, INDEX_AVL, INDEX_CAD, INDEX_DOCS,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("publish")

ALL_INDICES = [
    INDEX_PARTS, INDEX_BOM, INDEX_COSTING, INDEX_ECO,
    INDEX_AML, INDEX_AVL, INDEX_CAD, INDEX_DOCS,
]


def publish_index(backend, staging: StagingStore, index_name: str, force: bool) -> dict:
    """Ensure the index exists and bulk-publish its staged documents."""
    if not staging.exists(index_name):
        logger.warning(f"  No staged documents for {index_name}; skipping")
        return {"index": index_name, "staged": 0, "published": 0, "errors": 0}

    count = staging.count(index_name)
    logger.info(f"Publishing {index_name}: {count} staged documents")
    backend.ensure_index(index_name, force_recreate=force)

    docs = staging.read(index_name)
    published, errors = backend.bulk_index(index_name, docs)
    backend.refresh(index_name)  # make freshly indexed docs visible to search
    return {
        "index": index_name,
        "staged": count,
        "published": published,
        "errors": errors,
    }


def main():
    force = "--force" in sys.argv
    index_arg = None
    if "--index" in sys.argv:
        idx = sys.argv.index("--index") + 1
        if idx < len(sys.argv):
            index_arg = sys.argv[idx]

    # Prerequisite checks (embedding/ES config)
    for w in validate():
        logger.warning(w)

    try:
        backend = get_backend()
    except Exception as e:
        logger.error(f"Cannot initialize search backend: {e}")
        sys.exit(1)

    if not backend.health():
        logger.error("Search backend is not reachable. Stage with build_all "
                     "(--stage-only) and publish later once it is up.")
        sys.exit(1)

    targets = [index_arg] if index_arg else ALL_INDICES
    # Validate requested index name.
    if index_arg and index_arg not in ALL_INDICES:
        logger.error(f"Unknown index '{index_arg}'. Known: {ALL_INDICES}")
        sys.exit(1)

    staging = StagingStore()
    summary = []
    for index_name in targets:
        logger.info(f"{'=' * 50}")
        logger.info(f"Publishing index: {index_name}")
        logger.info(f"{'=' * 50}")
        try:
            result = publish_index(backend, staging, index_name, force=force)
            summary.append(result)
            logger.info(f"  Result: {result}")
        except Exception as e:
            logger.error(f"  FAILED: {e}")
            summary.append({"index": index_name, "error": str(e)})

    logger.info(f"\n{'=' * 50}")
    logger.info("PUBLISH SUMMARY")
    logger.info(f"{'=' * 50}")
    for r in summary:
        if "error" in r:
            logger.info(f"  {r['index']:20s} ❌ {r['error']}")
        else:
            logger.info(
                f"  {r['index']:20s} ✓ {r.get('published', 0)} published, "
                f"{r.get('errors', 0)} errors (of {r.get('staged', 0)} staged)"
            )


if __name__ == "__main__":
    main()

"""Run the full indexing pipeline: stage all entities, then publish.

Summary:
    Two-phase pipeline that decouples building from publishing:

    Phase 1 (stage)  — run every builder. Each reads its source (SQLAlchemy
                       model or PDFs), embeds, and writes backend-neutral JSONL
                       documents to the staging store. No search engine needed.
    Phase 2 (publish)— read the staged documents and push them to the active
                       SearchBackend in batches (bulk). Only this phase needs ES.

    Because the two phases are separate, you can stage offline (e.g.
    `build_all --stage-only`) and publish later once the search backend is up,
    or re-publish the same staging to a different backend. See publish.py.

    Usage:
        python -m db.indexing.build_all [--force] [--stage-only] [--publish-only] [--index NAME]

    Flags:
        --force         Phase 1: clear prior staging. Phase 2: recreate indices.
        --stage-only    Only run Phase 1 (produce staging files, no ES needed).
        --publish-only  Skip Phase 1; publish existing staging files.
        --index NAME    Limit to a single index (e.g. plm_parts, plm_docs).
"""

import sys
import logging
import time

from aisearch.config import validate
from db.indexing.staging import StagingStore
from aisearch.config import (
    INDEX_PARTS, INDEX_BOM, INDEX_COSTING, INDEX_ECO,
    INDEX_AML, INDEX_AVL, INDEX_CAD, INDEX_DOCS,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("build_all")

BUILDERS = [
    ("Parts", "db.indexing.build_parts", INDEX_PARTS),
    ("BOM", "db.indexing.build_bom", INDEX_BOM),
    ("Costing", "db.indexing.build_costing", INDEX_COSTING),
    ("ECO", "db.indexing.build_eco", INDEX_ECO),
    ("AML", "db.indexing.build_aml", INDEX_AML),
    ("AVL", "db.indexing.build_avl", INDEX_AVL),
    ("CAD", "db.indexing.build_cad", INDEX_CAD),
    ("Documents (PDFs)", "db.indexing.build_docs", INDEX_DOCS),
]

ALL_INDICES = [idx for _, _, idx in BUILDERS]


def _import_build(module_path: str):
    import importlib

    module = importlib.import_module(module_path)
    return module.build


def _run_stage(force: bool, index_filter: str | None) -> list[tuple[str, dict]]:
    summary = []
    for label, module_path, index_name in BUILDERS:
        if index_filter and index_name != index_filter:
            continue
        logger.info(f"{'=' * 50}")
        logger.info(f"Stage index: {label} ({index_name})")
        logger.info(f"{'=' * 50}")
        try:
            build_fn = _import_build(module_path)
            result = build_fn(force=force)
            summary.append((label, result))
            logger.info(f"  Result: {result}")
        except Exception as e:
            logger.error(f"  FAILED: {e}")
            summary.append((label, {"index": index_name, "error": str(e)}))
    return summary


def _run_publish(force: bool, index_filter: str | None) -> list[tuple[str, dict]]:
    from aisearch.backend import get_backend

    for w in validate():
        logger.warning(w)

    try:
        backend = get_backend()
    except Exception as e:
        logger.error(f"Cannot initialize search backend: {e}")
        sys.exit(1)

    if not backend.health():
        logger.error("Search backend is not reachable. Documents are staged; "
                     "run `python -m db.indexing.publish` once it is up.")
        sys.exit(1)

    from db.indexing.publish import publish_index

    staging = StagingStore()
    summary = []
    for label, _, index_name in BUILDERS:
        if index_filter and index_name != index_filter:
            continue
        logger.info(f"{'=' * 50}")
        logger.info(f"Publish index: {label} ({index_name})")
        logger.info(f"{'=' * 50}")
        try:
            result = publish_index(backend, staging, index_name, force=force)
            summary.append((label, result))
            logger.info(f"  Result: {result}")
        except Exception as e:
            logger.error(f"  FAILED: {e}")
            summary.append((label, {"index": index_name, "error": str(e)}))
    return summary


def _print_summary(title: str, summary: list[tuple[str, dict]]) -> None:
    logger.info(f"\n{'=' * 50}")
    logger.info(title)
    logger.info(f"{'=' * 50}")
    for label, result in summary:
        if "error" in result:
            logger.info(f"  {label:20s} ❌ {result['error']}")
        else:
            staged = result.get("staged", result.get("total", 0))
            published = result.get("published", result.get("staged", 0))
            errors = result.get("errors", 0)
            logger.info(f"  {label:20s} ✓ {published} published, {errors} errors "
                        f"(of {staged} staged)")


def main():
    t_start = time.time()
    force = "--force" in sys.argv
    stage_only = "--stage-only" in sys.argv
    publish_only = "--publish-only" in sys.argv

    index_filter = None
    if "--index" in sys.argv:
        idx = sys.argv.index("--index") + 1
        if idx < len(sys.argv):
            index_filter = sys.argv[idx]
            if index_filter not in ALL_INDICES:
                logger.error(f"Unknown index '{index_filter}'. Known: {ALL_INDICES}")
                sys.exit(1)

    if force:
        logger.info("Force mode enabled (fresh staging + index recreation)")

    if not publish_only:
        logger.info("PHASE 1: STAGE")
        stage_summary = _run_stage(force=force, index_filter=index_filter)
        _print_summary(f"STAGE SUMMARY ({time.time() - t_start:.1f}s)", stage_summary)

    if not stage_only:
        logger.info("PHASE 2: PUBLISH")
        t_pub = time.time()
        publish_summary = _run_publish(force=force, index_filter=index_filter)
        _print_summary(f"PUBLISH SUMMARY ({time.time() - t_pub:.1f}s)", publish_summary)

    logger.info(f"\nTOTAL ELAPSED: {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()

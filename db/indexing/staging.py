"""Intermediate staging store — the seam between indexing and search.

Summary:
    Builders (db/indexing/build_*.py) write fully-formed search documents to
    this store as backend-neutral JSONL, one file per index. A separate publish
    step (db/indexing/publish.py) reads these files and pushes them to whichever
    SearchBackend is configured.

    Because the on-disk format is just plain JSON documents (text fields +
    a precomputed `content_vector`), the search backend can be swapped (Elasticsearch,
    OpenSearch, Qdrant, ...) without changing any builder code. The staging files
    also make indexing resumable and decouple the (slow, rate-limited) embedding
    step from the (fast) publish step — ES can even be unavailable while staging.

Layout:
    <STAGING_DIR>/<index_name>.jsonl   one JSON document per line

Usage:
    with StagingStore() as staging:
        staging.reset(INDEX_PARTS)        # clear before a fresh build
        staging.stage(INDEX_PARTS, doc)   # append one document
    # ... later, in a different process / after ES is up:
    for doc in staging.read(INDEX_PARTS):
        publish(doc)
"""

import json
import logging
from pathlib import Path
from typing import Iterator, Optional

from aisearch.config import STAGING_DIR

logger = logging.getLogger(__name__)

_FLUSH_EVERY = 100  # lines written before forcing a flush to disk


class StagingStore:
    """Append-only JSONL store of index documents, partitioned by index name."""

    def __init__(self, staging_dir: Optional[Path] = None):
        self.staging_dir = Path(staging_dir or STAGING_DIR)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self._handles: dict[str, "object"] = {}
        self._counts: dict[str, int] = {}

    # ── Paths ──────────────────────────────────────────────────
    def _path(self, index_name: str) -> Path:
        # Sanitize so an index name can never escape the staging dir.
        safe = "".join(c for c in index_name if c.isalnum() or c in "-_.")
        return self.staging_dir / f"{safe}.jsonl"

    # ── Lifecycle ──────────────────────────────────────────────
    def reset(self, index_name: str) -> None:
        """Remove any existing staged documents for an index (fresh build)."""
        self.close(index_name)
        path = self._path(index_name)
        if path.exists():
            path.unlink()
            logger.debug(f"Reset staging for {index_name}")
        self._counts[index_name] = 0

    def _handle(self, index_name: str):
        if index_name not in self._handles:
            self._handles[index_name] = open(
                self._path(index_name), "w", encoding="utf-8"
            )
            self._counts[index_name] = 0
        return self._handles[index_name]

    def close(self, index_name: Optional[str] = None) -> None:
        """Flush and close open file handles (all, or just one index)."""
        names = [index_name] if index_name else list(self._handles.keys())
        for name in names:
            handle = self._handles.pop(name, None)
            if handle is not None:
                try:
                    handle.flush()
                    handle.close()
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning(f"Error closing staging handle for {name}: {e}")

    def __enter__(self) -> "StagingStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── Write ──────────────────────────────────────────────────
    def stage(self, index_name: str, doc: dict) -> None:
        """Append a single document to the index's staging file."""
        handle = self._handle(index_name)
        handle.write(json.dumps(doc, ensure_ascii=False) + "\n")
        self._counts[index_name] = self._counts.get(index_name, 0) + 1
        if self._counts[index_name] % _FLUSH_EVERY == 0:
            handle.flush()

    def stage_many(self, index_name: str, docs: Iterator[dict]) -> int:
        """Append many documents; returns the number staged."""
        n = 0
        for doc in docs:
            self.stage(index_name, doc)
            n += 1
        return n

    # ── Read ───────────────────────────────────────────────────
    def count(self, index_name: str) -> int:
        """Number of staged documents (in-memory if open, else counted on disk)."""
        if index_name in self._counts:
            return self._counts[index_name]
        path = self._path(index_name)
        if not path.exists():
            return 0
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def read(self, index_name: str) -> Iterator[dict]:
        """Yield staged documents for an index as dicts (empty if none)."""
        # Flush any open write handle so freshly staged docs are visible.
        handle = self._handles.get(index_name)
        if handle is not None:
            handle.flush()
        path = self._path(index_name)
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def exists(self, index_name: str) -> bool:
        return self._path(index_name).exists()

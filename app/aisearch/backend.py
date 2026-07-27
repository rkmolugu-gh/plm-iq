"""Search backend abstraction — the seam for swapping search engines.

Summary:
    All interaction with the search engine goes through the `SearchBackend`
    interface. The only shipped implementation is `ElasticsearchBackend`, but a
    new backend (OpenSearch, Qdrant, a local file search, ...) can be added by
    implementing the ABC and registering it in `get_backend()` — no builder or
    publish code needs to change, because both sides speak the same
    backend-neutral document format (see db/indexing/staging.py).

    Key methods:
    - ensure_index():  create an index if missing (recreate on force)
    - bulk_index():    push many documents efficiently (batched)
    - delete_index():  drop an index
    - index_exists():  existence check
    - health():        liveness probe used to fail fast before a publish
"""

import logging
from abc import ABC, abstractmethod
from typing import Iterable, Iterator, Optional

from .config import BULK_BATCH_SIZE, SEARCH_BACKEND

logger = logging.getLogger(__name__)


def _chunk(iterable: Iterable[dict], size: int) -> Iterator[list[dict]]:
    """Yield successive `size`-sized lists from an iterable of dicts."""
    batch: list[dict] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class SearchBackend(ABC):
    """Interface every search engine implementation must satisfy."""

    @abstractmethod
    def health(self) -> bool:
        """Return True if the backend is reachable and ready."""

    @abstractmethod
    def ensure_index(self, index_name: str, force_recreate: bool = False) -> None:
        """Ensure `index_name` exists; recreate it when force_recreate is set."""

    @abstractmethod
    def index_exists(self, index_name: str) -> bool:
        """Return True if the index currently exists."""

    @abstractmethod
    def delete_index(self, index_name: str) -> None:
        """Delete the index if it exists (no-op otherwise)."""

    @abstractmethod
    def bulk_index(
        self, index_name: str, docs: Iterable[dict], batch_size: int = BULK_BATCH_SIZE
    ) -> tuple[int, int]:
        """Push documents to the index in batches.

        Returns (success_count, error_count).
        """

    @abstractmethod
    def refresh(self, index_name: str) -> None:
        """Make recently indexed documents visible to search (refresh)."""


class ElasticsearchBackend(SearchBackend):
    """Elasticsearch implementation of SearchBackend.

    Delegates index creation/mapping to aisearch.es_client (which owns the
    ES-specific mapping definitions) and uses the bulk helper for throughput.
    """

    def __init__(self) -> None:
        # Late import keeps this module usable even if elasticsearch isn't installed.
        from . import es_client

        self._es_client = es_client
        self.es = es_client.get_es()

    def health(self) -> bool:
        try:
            self._es_client.get_es().info()
            return True
        except Exception as e:
            logger.warning(f"Elasticsearch health check failed: {e}")
            return False

    def index_exists(self, index_name: str) -> bool:
        return self.es.indices.exists(index=index_name)

    def ensure_index(self, index_name: str, force_recreate: bool = False) -> None:
        if force_recreate:
            # create_index handles delete-then-create internally.
            self._es_client.create_index(index_name, force_delete=True)
        elif not self.index_exists(index_name):
            self._es_client.create_index(index_name)

    def delete_index(self, index_name: str) -> None:
        if self.index_exists(index_name):
            self.es.indices.delete(index=index_name)
            logger.info(f"Deleted index: {index_name}")

    def bulk_index(
        self, index_name: str, docs: Iterable[dict], batch_size: int = BULK_BATCH_SIZE
    ) -> tuple[int, int]:
        from elasticsearch.helpers import BulkIndexError, bulk

        success_total = 0
        error_total = 0

        for batch in _chunk(docs, batch_size):
            actions = [{"_index": index_name, "_source": doc} for doc in batch]
            try:
                success, errors = bulk(
                    self.es, actions, raise_on_error=False, stats_only=False
                )
                success_total += success
                error_total += len(errors) if isinstance(errors, list) else 0
                if errors:
                    logger.warning(
                        f"  {index_name}: {len(errors)} bulk errors "
                        f"(first: {errors[0].get('index', {}).get('error')})"
                    )
            except BulkIndexError as e:
                # Partial success is still useful; record what we can.
                success_total += len(e.successful)
                error_total += len(e.failed)
                logger.error(f"  {index_name}: bulk indexing error: {e}")
            except Exception as e:
                logger.error(f"  {index_name}: bulk indexing failed: {e}")
                error_total += len(batch)

        return success_total, error_total

    def refresh(self, index_name: str) -> None:
        if self.index_exists(index_name):
            self.es.indices.refresh(index=index_name)


# ── Factory ─────────────────────────────────────────────────
_BACKENDS = {
    "elasticsearch": ElasticsearchBackend,
}


def get_backend(name: Optional[str] = None) -> SearchBackend:
    """Return the configured SearchBackend instance.

    Selection is driven by the SEARCH_BACKEND env var (default "elasticsearch").
    Add new engines by registering a SearchBackend subclass in _BACKENDS.
    """
    key = (name or SEARCH_BACKEND).lower()
    if key not in _BACKENDS:
        raise ValueError(
            f"Unknown SEARCH_BACKEND '{key}'. Known backends: {list(_BACKENDS)}"
        )
    return _BACKENDS[key]()

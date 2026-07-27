"""Base index builder — shared logic for staging SQLAlchemy models.

Summary:
    Provides BaseIndexBuilder which:
    1. Reads all rows from a SQLAlchemy model
    2. Converts each row to a searchable document dict (subclass: row_to_doc)
    3. Generates a `content_vector` embedding for the doc
    4. Stages the document to the backend-neutral JSONL store

    Subclasses override:
    - model_class: The SQLAlchemy model to read
    - index_name:  The target index name
    - row_to_doc(): Convert a DB row to a search document dict

    This builder knows nothing about the search engine — it only produces
    documents. Publishing to a SearchBackend happens later in publish.py, so the
    search platform can be swapped without touching builder code.
"""

import logging
from typing import Any
from sqlalchemy import text
from app.database import SessionLocal
from app.aisearch.config import MAX_EMBED_CHARS
from app.aisearch.llm_client import embed as generate_embedding
from db.indexing.staging import StagingStore

logger = logging.getLogger(__name__)


class BaseIndexBuilder:
    """Base class for staging an index from a SQLAlchemy model."""

    model_class = None          # Override in subclass
    index_name = None           # Override in subclass

    def build(self, force: bool = False) -> dict:
        """Read all rows from DB and stage them as search documents.

        Args:
            force: If True, clear any previously staged documents for this index
                before building (a fresh full rebuild of the staging file).

        Returns:
            dict with keys: index, total, staged, errors.
        """
        staging = StagingStore()
        if force:
            staging.reset(self.index_name)

        db = SessionLocal()
        try:
            rows = db.query(self.model_class).all()
            logger.info(f"Staging {self.index_name}: {len(rows)} rows from DB")

            success = 0
            errors = 0
            for row in rows:
                try:
                    doc = self.row_to_doc(row)
                    doc = self._add_embedding(doc)
                    staging.stage(self.index_name, doc)
                    success += 1
                except Exception as e:
                    errors += 1
                    logger.warning(f"  Error staging row in {self.index_name}: {e}")

                if (success + errors) % 50 == 0:
                    logger.debug(f"  Progress: {success} staged, {errors} errors")

            logger.info(f"  Done: {success} staged, {errors} errors")
            return {
                "index": self.index_name,
                "total": len(rows),
                "staged": success,
                "errors": errors,
            }
        finally:
            db.close()
            staging.close()

    def _add_embedding(self, doc: dict) -> dict:
        """Generate embedding vector for the doc's content and add it.

        The stored `content` is truncated to MAX_EMBED_CHARS before embedding so
        the indexed vector always corresponds to the text that is displayed and
        searched (the previous code truncated storage at 8k but embedding at 4k).

        Args:
            doc: Document dict with a 'content' key.

        Returns:
            The same doc with a 'content_vector' key added.
        """
        text_to_embed = doc.get("content", "")
        if not text_to_embed:
            return doc
        if len(text_to_embed) > MAX_EMBED_CHARS:
            text_to_embed = text_to_embed[:MAX_EMBED_CHARS]
            doc["content"] = text_to_embed
        doc["content_vector"] = generate_embedding(text_to_embed)
        return doc

    def row_to_doc(self, row: Any) -> dict:
        """Convert a DB row to a search document.

        Override this method in subclass.
        Must include at minimum: content, entity_type
        """
        raise NotImplementedError

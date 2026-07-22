"""Build plm_docs index — extract text from PDFs and stage them.

Summary:
    Reads PDF files from data/volume/, extracts text page by page, splits long
    pages into embedding-sized chunks, and stages each chunk as a searchable
    document. Each document has: filename, page_num, chunk_index, chunk_text,
    and entity_type. Documents are written to the backend-neutral staging store
    (no direct ES dependency); publishing happens later in publish.py.
"""

import logging
from pathlib import Path

from db.indexing.base import BaseIndexBuilder
from db.indexing.staging import StagingStore
from aisearch.config import INDEX_DOCS, VOLUME_DIR, MAX_EMBED_CHARS

logger = logging.getLogger(__name__)


class DocsIndexBuilder(BaseIndexBuilder):
    """Index PDF documents by extracting text and chunking by page."""

    model_class = None  # Not using SQLAlchemy
    index_name = INDEX_DOCS

    def build(self, force: bool = False):
        staging = StagingStore()
        if force:
            staging.reset(self.index_name)

        pdf_dir = Path(VOLUME_DIR)
        if not pdf_dir.exists():
            logger.warning(f"PDF volume directory not found: {pdf_dir}")
            return {"index": self.index_name, "total": 0, "staged": 0, "errors": 0}

        pdf_files = sorted(pdf_dir.glob("*.pdf"))
        logger.info(f"Staging {self.index_name}: {len(pdf_files)} PDFs found")

        success = 0
        errors = 0

        for pdf_path in pdf_files:
            try:
                pages = self._extract_pages(pdf_path)
                for page_num, text in pages:
                    chunks = self._chunk_text(text)
                    for chunk_idx, chunk in enumerate(chunks):
                        doc = self._page_to_doc(
                            pdf_path.name, page_num, chunk,
                            chunk_index=chunk_idx, total_chunks=len(chunks),
                        )
                        doc = self._add_embedding(doc)
                        staging.stage(self.index_name, doc)
                        success += 1
            except Exception as e:
                errors += 1
                logger.warning(f"  Error staging {pdf_path.name}: {e}")

            if (success + errors) % 20 == 0:
                logger.debug(f"  Progress: {success} chunks staged, {errors} errors")

        logger.info(f"  Done: {success} chunks from {len(pdf_files)} PDFs, {errors} errors")
        return {"index": self.index_name, "total": len(pdf_files), "staged": success, "errors": errors}

    def _extract_pages(self, pdf_path: Path) -> list[tuple[int, str]]:
        """Extract text from a PDF, returning list of (page_num, text) tuples."""
        try:
            import pypdf
        except ImportError:
            logger.error("pypdf not installed. Install with: pip install pypdf")
            return []

        pages = []
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            for i, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                text = text.strip()
                if len(text) > 20:  # Skip near-empty pages
                    pages.append((i, text))
        except Exception as e:
            logger.warning(f"  Error reading {pdf_path.name}: {e}")

        return pages

    def _chunk_text(self, text: str) -> list[str]:
        """Split long page text into embedding-sized chunks (<= MAX_EMBED_CHARS).

        This guarantees the stored `content` exactly matches what is embedded,
        and ensures long pages are fully covered rather than truncated.
        """
        if len(text) <= MAX_EMBED_CHARS:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + MAX_EMBED_CHARS
            chunks.append(text[start:end])
            start = end
        return chunks

    def _page_to_doc(
        self, filename: str, page_num: int, text: str,
        chunk_index: int = 0, total_chunks: int = 1,
    ) -> dict:
        """Convert extracted (chunked) page text to a staging document."""
        # Try to extract part number from filename (e.g., "BRK-001-A.pdf" → "BRK-001")
        part_number = ""
        parts = filename.replace(".pdf", "").split("-")
        if len(parts) >= 2:
            part_number = f"{parts[0]}-{parts[1]}"

        return {
            "content": text,
            "entity_type": "document",
            "filename": filename,
            "page_num": page_num,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "chunk_text": text[:500],  # Short preview for snippet display
            "part_number": part_number,
        }

    def row_to_doc(self, row) -> dict:
        raise NotImplementedError("DocsIndexBuilder uses build() directly")


def build(force: bool = False):
    return DocsIndexBuilder().build(force=force)

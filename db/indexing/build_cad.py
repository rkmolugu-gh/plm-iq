"""Build plm_cad index — index CAD metadata from SQLite.

Summary:
    Reads the cad_metadata table and creates searchable documents
    with CAD file names, formats, and drawing numbers.
"""

import logging
from db.indexing.base import BaseIndexBuilder
from app.aisearch.config import INDEX_CAD
from app.models import CadMetadata

logger = logging.getLogger(__name__)


class CadIndexBuilder(BaseIndexBuilder):
    model_class = CadMetadata
    index_name = INDEX_CAD

    def row_to_doc(self, row) -> dict:
        return {
            "content": f"{row.cad_file_name or ''} {row.cad_system or ''} {row.drawing_number or ''} {row.cad_file_format or ''} {row.part_number}",
            "entity_type": "cad",
            "tenant_id": row.tenant_id,  # Multi-tenant isolation
            "part_number": row.part_number,
            "part_revision": row.part_revision or "",
            "cad_file_name": row.cad_file_name or "",
            "cad_file_format": row.cad_file_format or "",
            "cad_system": row.cad_system or "",
            "file_reference_type": row.file_reference_type or "",
            "file_size_bytes": row.file_size_bytes or 0,
            "drawing_number": row.drawing_number or "",
        }


def build(force: bool = False):
    return CadIndexBuilder().build(force=force)

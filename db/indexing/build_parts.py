"""Build plm_parts index — index all parts from SQLite.

Summary:
    Reads the parts table and creates searchable documents with
    part_number, part_name, material, status, and spec_file.
"""

import logging
from db.indexing.base import BaseIndexBuilder
from app.aisearch.config import INDEX_PARTS
from app.models import Part

logger = logging.getLogger(__name__)


class PartsIndexBuilder(BaseIndexBuilder):
    model_class = Part
    index_name = INDEX_PARTS

    def row_to_doc(self, row) -> dict:
        return {
            "content": f"{row.part_number} {row.part_name} {row.material or ''} {row.spec_file or ''} {row.status or ''}",
            "entity_type": "part",
            "part_number": row.part_number,
            "part_revision": row.part_revision or "",
            "part_name": row.part_name or "",
            "material": row.material or "",
            "uom": row.uom or "",
            "qty": row.qty or 0,
            "status": row.status or "",
            "spec_file": row.spec_file or "",
        }


def build(force: bool = False):
    return PartsIndexBuilder().build(force=force)

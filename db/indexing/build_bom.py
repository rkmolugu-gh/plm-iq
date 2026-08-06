"""Build plm_bom index — index all BOM items from SQLite.

Summary:
    Reads the bom table and creates searchable documents with
    part_number, part_name, parent_assembly, and bom_type.
"""

import logging
from db.indexing.base import BaseIndexBuilder
from app.aisearch.config import INDEX_BOM
from app.models import BomItem

logger = logging.getLogger(__name__)


class BomIndexBuilder(BaseIndexBuilder):
    model_class = BomItem
    index_name = INDEX_BOM

    def row_to_doc(self, row) -> dict:
        return {
            "content": f"{row.part_number} {row.part_name or ''} {row.parent_assembly or ''} {row.bom_type or ''}",
            "entity_type": "bom",
            "tenant_key": row.tenant_key,  # Multi-tenant isolation
            "part_number": row.part_number,
            "part_revision": row.part_revision or "",
            "part_name": row.part_name or "",
            "qty": row.qty or 0,
            "uom": row.uom or "",
            "parent_assembly": row.parent_assembly or "",
            "bom_type": row.bom_type or "",
            "level": row.level or 0,
        }


def build(force: bool = False):
    return BomIndexBuilder().build(force=force)

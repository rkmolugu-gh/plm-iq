"""Build plm_eco index — index all engineering change orders from SQLite.

Summary:
    Reads the engineering_change_orders table and creates searchable
    documents with eco_number, title, description, status, and change details.
"""

import logging
from db.indexing.base import BaseIndexBuilder
from app.aisearch.config import INDEX_ECO
from app.models import EngineeringChangeOrder

logger = logging.getLogger(__name__)


class EcoIndexBuilder(BaseIndexBuilder):
    model_class = EngineeringChangeOrder
    index_name = INDEX_ECO

    def row_to_doc(self, row) -> dict:
        return {
            "content": f"{row.eco_number} {row.eco_title or ''} {row.eco_description or ''} {row.change_detail or ''} {row.part_number}",
            "entity_type": "eco",
            "tenant_key": row.tenant_key,  # Multi-tenant isolation
            "eco_number": row.eco_number,
            "eco_title": row.eco_title or "",
            "eco_description": row.eco_description or "",
            "eco_status": row.eco_status or "",
            "part_number": row.part_number or "",
            "change_type": row.change_type or "",
            "change_detail": row.change_detail or "",
            "current_revision": row.current_revision or "",
            "new_revision": row.new_revision or "",
        }


def build(force: bool = False):
    return EcoIndexBuilder().build(force=force)

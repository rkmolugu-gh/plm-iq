"""Build plm_aml index — index Approved Manufacturer List from SQLite.

Summary:
    Reads the approved_manufacturer_list table and creates searchable
    documents with manufacturer name, MPN, and part number.
"""

import logging
from db.indexing.base import BaseIndexBuilder
from app.aisearch.config import INDEX_AML
from app.models import ApprovedManufacturer

logger = logging.getLogger(__name__)


class AmlIndexBuilder(BaseIndexBuilder):
    model_class = ApprovedManufacturer
    index_name = INDEX_AML

    def row_to_doc(self, row) -> dict:
        return {
            "content": f"{row.part_number} {row.manufacturer_name or ''} {row.manufacturer_part_number or ''} Quality: {row.quality_rating or ''}",
            "entity_type": "aml",
            "tenant_key": row.tenant_key,  # Multi-tenant isolation
            "part_number": row.part_number,
            "manufacturer_name": row.manufacturer_name or "",
            "manufacturer_part_number": row.manufacturer_part_number or "",
            "preferred_flag": row.preferred_flag or "",
            "lead_time_days": row.lead_time_days,
            "unit_cost": float(row.unit_cost or 0),
            "quality_rating": row.quality_rating or "",
        }


def build(force: bool = False):
    return AmlIndexBuilder().build(force=force)

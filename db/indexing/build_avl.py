"""Build plm_avl index — index Approved Vendor List from SQLite.

Summary:
    Reads the approved_vendor_list table and creates searchable
    documents with vendor name, VPN, and part number.
"""

import logging
from db.indexing.base import BaseIndexBuilder
from app.aisearch.config import INDEX_AVL
from app.models import ApprovedVendor

logger = logging.getLogger(__name__)


class AvlIndexBuilder(BaseIndexBuilder):
    model_class = ApprovedVendor
    index_name = INDEX_AVL

    def row_to_doc(self, row) -> dict:
        return {
            "content": f"{row.part_number} {row.vendor_name or ''} {row.vendor_part_number or ''}",
            "entity_type": "avl",
            "part_number": row.part_number,
            "vendor_name": row.vendor_name or "",
            "vendor_part_number": row.vendor_part_number or "",
            "preferred_flag": row.preferred_flag or "",
            "unit_price": float(row.unit_price or 0),
            "min_order_qty": row.min_order_qty,
            "lead_time_days": row.lead_time_days,
            "iso_certified": row.iso_certified or "",
        }


def build(force: bool = False):
    return AvlIndexBuilder().build(force=force)

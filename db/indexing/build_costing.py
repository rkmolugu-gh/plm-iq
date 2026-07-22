"""Build plm_costing index — index all costing BOM items from SQLite.

Summary:
    Reads the costing_bom table and creates searchable documents with
    part_number, part_name, cost_type, and cost breakdown values.
"""

import logging
from db.indexing.base import BaseIndexBuilder
from aisearch.config import INDEX_COSTING
from app.models import CostingBomItem

logger = logging.getLogger(__name__)


class CostingIndexBuilder(BaseIndexBuilder):
    model_class = CostingBomItem
    index_name = INDEX_COSTING

    def row_to_doc(self, row) -> dict:
        return {
            "content": f"{row.part_number} {row.part_name or ''} {row.cost_type or ''} Cost: material={row.material_cost} labor={row.labor_cost} overhead={row.overhead_cost} unit={row.unit_cost} total={row.rolled_total}",
            "entity_type": "costing",
            "part_number": row.part_number,
            "part_name": row.part_name or "",
            "qty": row.qty or 0,
            "uom": row.uom or "",
            "cost_type": row.cost_type or "",
            "material_cost": float(row.material_cost or 0),
            "labor_cost": float(row.labor_cost or 0),
            "overhead_cost": float(row.overhead_cost or 0),
            "unit_cost": float(row.unit_cost or 0),
            "rolled_total": float(row.rolled_total or 0),
        }


def build(force: bool = False):
    return CostingIndexBuilder().build(force=force)

"""PLM tool functions for LLM tool calling — read, create, and update PLM entities.

Independent module for the PLM Assistant. Provides tools for all PLM entities:
Parts, BOM, Costing, ECO, AML, AVL, and CAD. Each tool has a JSON Schema
definition for LLM function calling and a Python function that executes the
operation against the database.

This is a self-contained copy — no imports from aisearch/plm_tools.py.
"""

import logging
import re
from datetime import datetime
from typing import Optional

from app.database import SessionLocal
from app.models.parts import Part
from app.models.bom import BomItem
from app.models.costing import CostingBomItem
from app.models.eco import EngineeringChangeOrder
from app.models.aml import ApprovedManufacturer
from app.models.avl import ApprovedVendor
from app.models.cad import CadMetadata
from app.models.tenant_user import User, Tenant

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Tool Definitions (JSON Schema for LLM)
# ═══════════════════════════════════════════════════════════════════

GET_PART_TOOL = {
    "type": "function",
    "function": {
        "name": "get_part",
        "description": "Look up a part by its part number and return all details (name, revision, material, status, costs, relationships).",
        "parameters": {
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "The part number to look up (e.g. BB-001, FRM-003)",
                }
            },
            "required": ["part_number"],
            "additionalProperties": False,
        },
    },
}

SEARCH_PARTS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_parts",
        "description": "Search for parts by name, number, or material. Returns a list of matching parts with key details. Use this when the user isn't sure of the exact part number.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term — matches against part_number, part_name, and material (e.g. 'BB-001', 'Frame', 'Aluminum')",
                },
                "status": {
                    "type": "string",
                    "description": "Optional status filter: DRAFT, RELEASED, or OBSOLETED",
                    "enum": ["DRAFT", "RELEASED", "OBSOLETED"],
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

CREATE_PART_TOOL = {
    "type": "function",
    "function": {
        "name": "create_part",
        "description": "Create a new part based on a template part with optional field overrides. The new part number is auto-generated (e.g. BB-001 -> BB-007). You can also specify the part_number explicitly.",
        "parameters": {
            "type": "object",
            "properties": {
                "template_part": {
                    "type": "string",
                    "description": "The part number to use as a template (e.g. BB-001). All fields from this part will be copied over.",
                },
                "part_number": {
                    "type": "string",
                    "description": "Optional explicit part number (e.g. BB-010). If not provided, the next available number in the prefix sequence is auto-generated.",
                },
                "overrides": {
                    "type": "object",
                    "description": "Optional field overrides to customize the new part.",
                    "properties": {
                        "part_name": {"type": "string", "description": "New part name"},
                        "material": {"type": "string", "description": "New material"},
                        "status": {"type": "string", "description": "Status: DRAFT, RELEASED, or OBSOLETED"},
                        "uom": {"type": "string", "description": "Unit of measure (e.g. EA, KG, M)"},
                        "qty": {"type": "integer", "description": "Quantity"},
                        "spec_file": {"type": "string", "description": "Specification file reference"},
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["template_part"],
            "additionalProperties": False,
        },
    },
}

UPDATE_PART_STATUS_TOOL = {
    "type": "function",
    "function": {
        "name": "update_part_status",
        "description": "Update the status of an existing part (e.g. change from DRAFT to RELEASED).",
        "parameters": {
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "The part number to update (e.g. BB-001)",
                },
                "status": {
                    "type": "string",
                    "description": "New status value",
                    "enum": ["DRAFT", "RELEASED", "OBSOLETED"],
                },
            },
            "required": ["part_number", "status"],
            "additionalProperties": False,
        },
    },
}

GET_BOM_TOOL = {
    "type": "function",
    "function": {
        "name": "get_bom",
        "description": "Get the Bill of Materials for a part — shows all sub-components, quantities, and assembly structure. Use this when asked about what a part is made of, its components, or BOM structure.",
        "parameters": {
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "The part number to look up the BOM for (e.g. BB-001)",
                },
                "bom_type": {
                    "type": "string",
                    "description": "Optional BOM type filter: DESIGN, AS_BUILT, AS_SHIPPED, or AS_MAINTAINED",
                    "enum": ["DESIGN", "AS_BUILT", "AS_SHIPPED", "AS_MAINTAINED"],
                },
            },
            "required": ["part_number"],
            "additionalProperties": False,
        },
    },
}

GET_COSTING_TOOL = {
    "type": "function",
    "function": {
        "name": "get_costing",
        "description": "Get costing details for a part — material cost, labor cost, overhead, machining cost, unit cost, and rolled total. Use this when asked about costs, pricing, or financial details of a part.",
        "parameters": {
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "The part number to look up costing for (e.g. BB-001)",
                },
            },
            "required": ["part_number"],
            "additionalProperties": False,
        },
    },
}

GET_ECO_TOOL = {
    "type": "function",
    "function": {
        "name": "get_eco",
        "description": "Look up an Engineering Change Order by its ECO number. Returns the ECO title, description, status, affected part, change type, and approval dates.",
        "parameters": {
            "type": "object",
            "properties": {
                "eco_number": {
                    "type": "string",
                    "description": "The ECO number to look up (e.g. ECO-001)",
                },
            },
            "required": ["eco_number"],
            "additionalProperties": False,
        },
    },
}

SEARCH_ECOS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_ecos",
        "description": "Search Engineering Change Orders by part number, title, or status. Use this when the user asks about changes affecting a specific part or wants to find ECOs.",
        "parameters": {
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "Optional part number to find ECOs affecting this part (e.g. BB-001)",
                },
                "status": {
                    "type": "string",
                    "description": "Optional status filter: DRAFT, REVIEW, or APPROVED",
                    "enum": ["DRAFT", "REVIEW", "APPROVED"],
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}

GET_AML_TOOL = {
    "type": "function",
    "function": {
        "name": "get_aml",
        "description": "Get the Approved Manufacturer List for a part — manufacturers that are approved to supply this part, including part numbers, lead times, costs, and quality ratings.",
        "parameters": {
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "The part number to look up approved manufacturers for (e.g. BB-001)",
                },
                "preferred_only": {
                    "type": "boolean",
                    "description": "If true, only return preferred manufacturers",
                },
            },
            "required": ["part_number"],
            "additionalProperties": False,
        },
    },
}

GET_AVL_TOOL = {
    "type": "function",
    "function": {
        "name": "get_avl",
        "description": "Get the Approved Vendor List for a part — vendors that are approved to supply this part, including pricing, lead times, MOQ, ISO certification, and payment terms.",
        "parameters": {
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "The part number to look up approved vendors for (e.g. BB-001)",
                },
                "preferred_only": {
                    "type": "boolean",
                    "description": "If true, only return preferred vendors",
                },
            },
            "required": ["part_number"],
            "additionalProperties": False,
        },
    },
}

GET_CAD_TOOL = {
    "type": "function",
    "function": {
        "name": "get_cad",
        "description": "Get CAD file metadata for a part — file names, formats (SLDASM, STEP, DWG, PDF), CAD system, modeling author, and file references. Use this when asked about CAD files, drawings, or 3D models.",
        "parameters": {
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "The part number to look up CAD files for (e.g. BB-001)",
                },
            },
            "required": ["part_number"],
            "additionalProperties": False,
        },
    },
}

# ── All tools the agent can use ───────────────────────────────────
ALL_TOOLS = [
    GET_PART_TOOL,
    SEARCH_PARTS_TOOL,
    CREATE_PART_TOOL,
    UPDATE_PART_STATUS_TOOL,
    GET_BOM_TOOL,
    GET_COSTING_TOOL,
    GET_ECO_TOOL,
    SEARCH_ECOS_TOOL,
    GET_AML_TOOL,
    GET_AVL_TOOL,
    GET_CAD_TOOL,
]


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"
def _next_part_number(prefix: str) -> str:
    """Find the next available part number for a given prefix (e.g. 'BB' -> 'BB-007')."""
    db = SessionLocal()
    try:
        pattern = f"{prefix}-%"
        parts = db.query(Part.part_number).filter(Part.part_number.like(pattern)).all()
        max_num = 0
        for (pn,) in parts:
            m = re.search(rf"^{re.escape(prefix)}-(\d+)$", pn)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
        next_num = max_num + 1
        return f"{prefix}-{next_num:03d}"
    finally:
        db.close()


def _fmt_currency(value) -> str:
    """Format a numeric value as a currency string."""
    if value is None:
        return "-"
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return str(value)


def _resolve_user_id(db, candidate) -> Optional[int]:
    """Return a valid users.user_id or None."""
    user_id = None

    # Try numeric id first
    if isinstance(candidate, int):
        user_id = candidate
    elif isinstance(candidate, str):
        c = candidate.strip()
        if c.isdigit():
            user_id = int(c)
        elif c:
            # Legacy datasets may store username in modified_owner.
            user = db.query(User).filter(User.username == c).first()
            if user:
                return user.user_id

    if user_id is not None:
        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            return user.user_id

    # Safe fallback: first active user
    fallback = db.query(User).filter(User.is_active.is_(True)).order_by(User.user_id).first()
    if fallback:
        return fallback.user_id
    return None


def _resolve_tenant_id(db, candidate) -> Optional[int]:
    """Return a valid tenants.tenant_id or None."""
    tenant_id = None
    if isinstance(candidate, int):
        tenant_id = candidate
    elif isinstance(candidate, str):
        c = candidate.strip()
        if c.isdigit():
            tenant_id = int(c)

    if tenant_id is not None:
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if tenant:
            return tenant.tenant_id

    fallback = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.tenant_id).first()
    if fallback:
        return fallback.tenant_id
    return None


def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments and return a result string."""
    logger.info(f"[plmassistant] Executing tool: {tool_name}({arguments})")

    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown tool: {tool_name}. Available: {list(TOOL_REGISTRY.keys())}")
    return fn(**arguments)


# ── Part tools ────────────────────────────────────────────────────

def _execute_get_part(part_number: str) -> str:
    db = SessionLocal()
    try:
        part = db.query(Part).filter(Part.part_number == part_number).first()
        if not part:
            return f"Error: Part '{part_number}' not found."

        return (
            f"Part details:\n"
            f"  part_number: {part.part_number}\n"
            f"  part_revision: {part.part_revision}\n"
            f"  part_name: {part.part_name}\n"
            f"  spec_file: {part.spec_file or '-'}\n"
            f"  material: {part.material or '-'}\n"
            f"  uom: {part.uom}\n"
            f"  qty: {part.qty}\n"
            f"  status: {part.status}\n"
            f"  created_date: {part.created_date or '-'}\n"
            f"  modified_date: {part.modified_date or '-'}\n"
            f"  modified_owner: {part.modified_owner or '-'}"
        )
    finally:
        db.close()


def _execute_search_parts(query: str, status: Optional[str] = None) -> str:
    db = SessionLocal()
    try:
        q = db.query(Part).filter(
            Part.part_number.ilike(f"%{query}%")
            | Part.part_name.ilike(f"%{query}%")
            | Part.material.ilike(f"%{query}%")
        )
        if status:
            q = q.filter(Part.status == status)

        results = q.order_by(Part.part_number).limit(20).all()
        if not results:
            return f"No parts found matching '{query}'."

        lines = [f"Found {len(results)} part(s):"]
        for p in results:
            lines.append(
                f"  - {p.part_number} | {p.part_name} | rev {p.part_revision} | "
                f"{p.material or '-'} | status: {p.status}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def _execute_create_part(
    template_part: str,
    overrides: Optional[dict] = None,
    part_number: Optional[str] = None,
) -> str:
    overrides = overrides or {}
    db = SessionLocal()
    try:
        template = db.query(Part).filter(Part.part_number == template_part).first()
        if not template:
            return f"Error: Template part '{template_part}' not found."

        if part_number:
            new_part_number = part_number
            existing = db.query(Part).filter(Part.part_number == new_part_number).first()
            if existing:
                return f"Error: Part '{new_part_number}' already exists."
        else:
            prefix = template_part.split("-")[0]
            new_part_number = _next_part_number(prefix)

        now_str = datetime.now().strftime("%d-%m-%Y")
        resolved_created_by = _resolve_user_id(db, template.created_by)
        resolved_modified_owner = _resolve_user_id(db, template.modified_owner)
        resolved_tenant_id = _resolve_tenant_id(db, template.tenant_id)

        if resolved_tenant_id is None:
            return (
                "Error creating part: No valid tenant found for foreign key "
                "(tenants.tenant_id)."
            )

        new_part = Part(
            part_number=new_part_number,
            part_revision=overrides.get("part_revision", template.part_revision),
            part_name=overrides.get("part_name", template.part_name),
            spec_file=overrides.get("spec_file", template.spec_file),
            material=overrides.get("material", template.material),
            uom=overrides.get("uom", template.uom),
            qty=overrides.get("qty", template.qty),
            status=overrides.get("status", "DRAFT"),
            created_date=now_str,
            modified_date=now_str,
            modified_owner=resolved_modified_owner,
            created_by=resolved_created_by,
            tenant_id=resolved_tenant_id,
        )

        db.add(new_part)
        db.commit()

        return (
            f"Successfully created new part based on '{template_part}'.\n"
            f"  part_number: {new_part.part_number}\n"
            f"  part_name: {new_part.part_name}\n"
            f"  material: {new_part.material or '-'}\n"
            f"  uom: {new_part.uom}\n"
            f"  qty: {new_part.qty}\n"
            f"  status: {new_part.status}"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create part: {e}")
        return f"Error creating part: {e}"
    finally:
        db.close()


def _execute_update_part_status(part_number: str, status: str) -> str:
    db = SessionLocal()
    try:
        part = db.query(Part).filter(Part.part_number == part_number).first()
        if not part:
            return f"Error: Part '{part_number}' not found."

        old_status = part.status
        part.status = status
        part.modified_date = datetime.now().strftime("%d-%m-%Y")
        db.commit()

        return (
            f"Part '{part_number}' status updated: {old_status} -> {status}"
        )
    except Exception as e:
        db.rollback()
        return f"Error updating part status: {e}"
    finally:
        db.close()


# ── BOM tools ─────────────────────────────────────────────────────

def _execute_get_bom(part_number: str, bom_type: Optional[str] = None) -> str:
    db = SessionLocal()
    try:
        q = db.query(BomItem).filter(
            (BomItem.part_number == part_number)
            | (BomItem.parent_assembly == part_number)
        )
        if bom_type:
            q = q.filter(BomItem.bom_type == bom_type)

        items = q.order_by(BomItem.level, BomItem.part_number).all()
        if not items:
            return f"No BOM items found for part '{part_number}'."

        lines = [f"Bill of Materials for {part_number} ({len(items)} items):"]
        for item in items:
            lines.append(
                f"  [L{item.level}] {item.part_number} | {item.part_name or '-'} | "
                f"qty: {item.qty} {item.uom or ''} | parent: {item.parent_assembly or '-'} | "
                f"type: {item.bom_type}"
            )
        return "\n".join(lines)
    finally:
        db.close()


# ── Costing tools ─────────────────────────────────────────────────

def _execute_get_costing(part_number: str) -> str:
    db = SessionLocal()
    try:
        items = (
            db.query(CostingBomItem)
            .filter(CostingBomItem.part_number == part_number)
            .order_by(CostingBomItem.level)
            .all()
        )
        if not items:
            return f"No costing data found for part '{part_number}'."

        lines = [f"Costing details for {part_number} ({len(items)} entries):"]
        totals = {"material": 0, "labor": 0, "overhead": 0, "machining": 0, "rolled": 0}
        for item in items:
            lines.append(
                f"  {item.part_name or item.part_number} (L{item.level}, qty {item.qty}):\n"
                f"    material: {_fmt_currency(item.material_cost)} | "
                f"labor: {_fmt_currency(item.labor_cost)} | "
                f"overhead: {_fmt_currency(item.overhead_cost)}\n"
                f"    machining: {_fmt_currency(item.machining_cost)} | "
                f"unit: {_fmt_currency(item.unit_cost)} | "
                f"extended: {_fmt_currency(item.extended_cost)}\n"
                f"    rolled total: {_fmt_currency(item.rolled_total)} | "
                f"type: {item.cost_type}"
            )
            totals["material"] += float(item.material_cost or 0)
            totals["labor"] += float(item.labor_cost or 0)
            totals["overhead"] += float(item.overhead_cost or 0)
            totals["machining"] += float(item.machining_cost or 0)
            totals["rolled"] += float(item.rolled_total or 0)

        lines.append(
            f"  --- Totals ---\n"
            f"  material: {_fmt_currency(totals['material'])} | "
            f"labor: {_fmt_currency(totals['labor'])} | "
            f"overhead: {_fmt_currency(totals['overhead'])}\n"
            f"  machining: {_fmt_currency(totals['machining'])} | "
            f"rolled total: {_fmt_currency(totals['rolled'])}"
        )
        return "\n".join(lines)
    finally:
        db.close()


# ── ECO tools ─────────────────────────────────────────────────────

def _execute_get_eco(eco_number: str) -> str:
    db = SessionLocal()
    try:
        eco = (
            db.query(EngineeringChangeOrder)
            .filter(EngineeringChangeOrder.eco_number == eco_number)
            .first()
        )
        if not eco:
            return f"Error: ECO '{eco_number}' not found."

        return (
            f"Engineering Change Order {eco.eco_number}:\n"
            f"  title: {eco.eco_title}\n"
            f"  description: {eco.eco_description or '-'}\n"
            f"  status: {eco.eco_status}\n"
            f"  part_number: {eco.part_number}\n"
            f"  current_revision: {eco.current_revision or '-'}\n"
            f"  new_revision: {eco.new_revision or '-'}\n"
            f"  change_type: {eco.change_type or '-'}\n"
            f"  change_detail: {eco.change_detail or '-'}\n"
            f"  drafted_date: {eco.drafted_date or '-'}\n"
            f"  approved_date: {eco.approved_date or '-'}\n"
            f"  implemented_date: {eco.implemented_date or '-'}\n"
            f"  new_status: {eco.new_status or '-'}"
        )
    finally:
        db.close()


def _execute_search_ecos(part_number: Optional[str] = None, status: Optional[str] = None) -> str:
    db = SessionLocal()
    try:
        q = db.query(EngineeringChangeOrder)
        if part_number:
            q = q.filter(EngineeringChangeOrder.part_number == part_number)
        if status:
            q = q.filter(EngineeringChangeOrder.eco_status == status)

        results = q.order_by(EngineeringChangeOrder.drafted_date.desc().nullsfirst()).limit(20).all()
        if not results:
            msg = "No ECOs found"
            if part_number:
                msg += f" for part '{part_number}'"
            if status:
                msg += f" with status '{status}'"
            return msg + "."

        lines = [f"Found {len(results)} ECO(s):"]
        for eco in results:
            lines.append(
                f"  - {eco.eco_number} | {eco.eco_title} | {eco.eco_status} | "
                f"part: {eco.part_number} | type: {eco.change_type or '-'} | "
                f"drafted: {eco.drafted_date or '-'}"
            )
        return "\n".join(lines)
    finally:
        db.close()


# ── AML tools ─────────────────────────────────────────────────────

def _execute_get_aml(part_number: str, preferred_only: bool = False) -> str:
    db = SessionLocal()
    try:
        q = db.query(ApprovedManufacturer).filter(
            ApprovedManufacturer.part_number == part_number
        )
        if preferred_only:
            q = q.filter(ApprovedManufacturer.preferred_flag == "Yes")

        items = q.order_by(ApprovedManufacturer.manufacturer_name).all()
        if not items:
            return f"No approved manufacturers found for part '{part_number}'."

        lines = [f"Approved Manufacturers for {part_number} ({len(items)} entries):"]
        for aml in items:
            lines.append(
                f"  - {aml.manufacturer_name}{' [PREFERRED]' if aml.preferred_flag == 'Yes' else ''}\n"
                f"    mfr part#: {aml.manufacturer_part_number or '-'} | "
                f"status: {aml.manufacturer_status}\n"
                f"    lead time: {aml.lead_time_days or '-'} days | "
                f"cost: {_fmt_currency(aml.unit_cost)} {aml.currency or 'USD'}\n"
                f"    quality: {aml.quality_rating or '-'} | "
                f"compliance: {aml.compliance_status or '-'} | "
                f"source: {aml.source_type}\n"
                f"    notes: {aml.notes or '-'}"
            )
        return "\n".join(lines)
    finally:
        db.close()


# ── AVL tools ─────────────────────────────────────────────────────

def _execute_get_avl(part_number: str, preferred_only: bool = False) -> str:
    db = SessionLocal()
    try:
        q = db.query(ApprovedVendor).filter(
            ApprovedVendor.part_number == part_number
        )
        if preferred_only:
            q = q.filter(ApprovedVendor.preferred_flag == "Yes")

        items = q.order_by(ApprovedVendor.vendor_name).all()
        if not items:
            return f"No approved vendors found for part '{part_number}'."

        lines = [f"Approved Vendors for {part_number} ({len(items)} entries):"]
        for avl in items:
            lines.append(
                f"  - {avl.vendor_name}{' [PREFERRED]' if avl.preferred_flag == 'Yes' else ''}\n"
                f"    vendor part#: {avl.vendor_part_number or '-'} | "
                f"status: {avl.vendor_status}\n"
                f"    lead time: {avl.lead_time_days or '-'} days | "
                f"price: {_fmt_currency(avl.unit_price)} {avl.currency or 'USD'}\n"
                f"    MOQ: {avl.min_order_qty or 1} {avl.moq_uom or ''} | "
                f"ISO: {avl.iso_certified or '-'}\n"
                f"    payment: {avl.payment_terms or '-'} | "
                f"shipping: {avl.shipping_method or '-'}\n"
                f"    contract: {avl.contract_number or '-'} | "
                f"site: {avl.vendor_site or '-'}\n"
                f"    notes: {avl.notes or '-'}"
            )
        return "\n".join(lines)
    finally:
        db.close()


# ── CAD tools ─────────────────────────────────────────────────────

def _execute_get_cad(part_number: str) -> str:
    db = SessionLocal()
    try:
        items = (
            db.query(CadMetadata)
            .filter(CadMetadata.part_number == part_number)
            .order_by(CadMetadata.cad_file_name)
            .all()
        )
        if not items:
            return f"No CAD files found for part '{part_number}'."

        lines = [f"CAD files for {part_number} ({len(items)} entries):"]
        for cad in items:
            lines.append(
                f"  - {cad.cad_file_name} ({cad.cad_file_format})\n"
                f"    system: {cad.cad_system or '-'} v{cad.cad_version or '-'} | "
                f"type: {cad.model_type or '-'}\n"
                f"    reference: {cad.file_reference_type} | "
                f"drawing#: {cad.drawing_number or '-'}\n"
                f"    size: {_fmt_size(cad.file_size_bytes) if cad.file_size_bytes else '-'}\n"
                f"    source: {cad.source_type or '-'} | "
                f"notes: {cad.notes or '-'}"
            )
        return "\n".join(lines)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
# Tool Execution — registry of all available tools
# ═══════════════════════════════════════════════════════════════════

TOOL_REGISTRY = {
    "get_part": _execute_get_part,
    "search_parts": _execute_search_parts,
    "create_part": _execute_create_part,
    "update_part_status": _execute_update_part_status,
    "get_bom": _execute_get_bom,
    "get_costing": _execute_get_costing,
    "get_eco": _execute_get_eco,
    "search_ecos": _execute_search_ecos,
    "get_aml": _execute_get_aml,
    "get_avl": _execute_get_avl,
    "get_cad": _execute_get_cad,
}

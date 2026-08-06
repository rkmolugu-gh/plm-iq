"""PLM tool functions for LLM tool calling — create, read, update PLM entities.

Summary:
    Defines tools that the LLM can invoke during chat. Each tool has:
    - A JSON Schema definition (for the LLM to understand parameters)
    - A Python function that executes the operation against the DB

    Tools currently implemented:
        - get_part(template_part): Look up an existing part's full details
        - create_part(template_part, overrides): Create a new part based on a template
"""

import logging
import re
from datetime import datetime
from typing import Optional

from app.database import SessionLocal, TenantScopedSession
from app.models.parts import Part

logger = logging.getLogger(__name__)

# ── Tool Definitions (JSON Schema for LLM) ───────────────────────

GET_PART_TOOL = {
    "type": "function",
    "function": {
        "name": "get_part",
        "description": "Look up a part by its part number and return all its details (name, revision, material, status, etc.)",
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

CREATE_PART_TOOL = {
    "type": "function",
    "function": {
        "name": "create_part",
        "description": "Create a new part based on a template part with optional field overrides. The new part number is auto-generated (e.g. BB-001 → BB-007). You can also specify the part_number explicitly if you know the exact next number.",
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
                    "description": "Optional field overrides to customize the new part. Only include fields you want to change from the template.",
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

ALL_TOOLS = [GET_PART_TOOL, CREATE_PART_TOOL]

# ── Tool Execution ────────────────────────────────────────────────

TOOL_REGISTRY = {
    "get_part": "execute_get_part",
    "create_part": "execute_create_part",
}


def _next_part_number(prefix: str, tenant_key: str | None = None) -> str:
    """Find the next available part number for a given prefix (e.g. 'BB' → 'BB-007')."""
    db = TenantScopedSession(SessionLocal(), tenant_key)
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


def execute_tool(tool_name: str, arguments: dict, tenant_key: str | None = None) -> str:
    """Execute a tool by name with the given arguments and return a result string."""
    logger.info(f"Executing tool: {tool_name}({arguments})")

    if tool_name == "get_part":
        return _execute_get_part(**arguments, tenant_key=tenant_key)
    elif tool_name == "create_part":
        return _execute_create_part(**arguments, tenant_key=tenant_key)
    else:
        raise ValueError(f"Unknown tool: {tool_name}")


def _execute_get_part(part_number: str, tenant_key: str | None = None) -> str:
    """Look up a part and return its details as a formatted string."""
    db = TenantScopedSession(SessionLocal(), tenant_key)
    try:
        part = db.query(Part).filter(Part.part_number == part_number).first()
        if not part:
            return f"Error: Part '{part_number}' not found."

        fields = [
            f"part_number: {part.part_number}",
            f"part_revision: {part.part_revision}",
            f"part_name: {part.part_name}",
            f"spec_file: {part.spec_file or '-'}",
            f"material: {part.material or '-'}",
            f"uom: {part.uom}",
            f"qty: {part.qty}",
            f"status: {part.status}",
            f"created_date: {part.created_date or '-'}",
            f"modified_date: {part.modified_date or '-'}",
            f"modified_owner: {part.modified_owner or '-'}",
            f"created_by: {part.created_by or '-'}",
            f"tenant_id: {part.tenant_id or '-'}",
        ]
        return "Part details:\n" + "\n".join(fields)
    finally:
        db.close()


def _execute_create_part(
    template_part: str,
    overrides: Optional[dict] = None,
    part_number: Optional[str] = None,
    tenant_key: str | None = None,
) -> str:
    """Create a new part based on a template part with optional overrides."""
    overrides = overrides or {}

    db = TenantScopedSession(SessionLocal(), tenant_key)
    try:
        # 1. Look up the template part
        template = db.query(Part).filter(Part.part_number == template_part).first()
        if not template:
            return f"Error: Template part '{template_part}' not found."

        # 2. Determine the new part number
        if part_number:
            new_part_number = part_number
            # Check if it already exists
            existing = db.query(Part).filter(Part.part_number == new_part_number).first()
            if existing:
                return f"Error: Part '{new_part_number}' already exists."
        else:
            # Auto-generate from template prefix
            prefix = template_part.split("-")[0]
            new_part_number = _next_part_number(prefix, tenant_key=tenant_key)

        # 3. Build the new part from template + overrides
        now_str = datetime.now().strftime("%d-%m-%Y")
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
            modified_owner=template.modified_owner,
            created_by=template.created_by or 1,
            tenant_id=template.tenant_id or 1,
            tenant_key=tenant_key or template.tenant_key,
        )

        db.add(new_part)
        db.commit()

        created_fields = [
            f"part_number: {new_part.part_number}",
            f"part_name: {new_part.part_name}",
            f"material: {new_part.material or '-'}",
            f"uom: {new_part.uom}",
            f"qty: {new_part.qty}",
            f"status: {new_part.status}",
        ]
        return (
            f"Successfully created new part based on '{template_part}'.\n"
            + "\n".join(created_fields)
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create part: {e}")
        return f"Error creating part: {e}"
    finally:
        db.close()
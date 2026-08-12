"""PLM-IQ MCP Server — exposes PLM tools via Model Context Protocol.

This server wraps the existing PLM Assistant tools (from app/plmassistant/plm_tools.py)
and exposes them via MCP, allowing Claude Desktop and other MCP clients to
interact with PLM-IQ data.

Setup:
  1. Add to Claude Desktop config (see README.md in this folder)
  2. Restart Claude Desktop
  3. PLM tools will appear in Claude's tool menu

Usage:
  # Run with MCP Inspector for testing
  npx @modelcontextprotocol/inspector python plm_mcp/server.py

  # Or run directly (stdio mode)
  python plm_mcp/server.py
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

# ── Find project root (parent of plm_mcp folder) ──────────────────
PROJECT_ROOT = Path(__file__).parent.parent

# ── Load .env before importing app modules ─────────────────────────
_dotenv_path = PROJECT_ROOT / ".env"
if _dotenv_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_dotenv_path)

# ── Fix relative database path ──────────────────────────────────────
# The .env may have a relative DATABASE_URL like sqlite:///db/plm-iq.db
# When Claude Desktop runs this server, the working directory may differ
# so we need to convert it to an absolute path
_database_url = os.environ.get("DATABASE_URL", "")
if _database_url.startswith("sqlite:///"):
    _db_path = _database_url.replace("sqlite:///", "")
    if not Path(_db_path).is_absolute():
        # Convert to absolute path relative to PROJECT_ROOT
        _absolute_db_path = (PROJECT_ROOT / _db_path).resolve()
        # Use forward slashes for SQLite compatibility
        _absolute_db_path_str = str(_absolute_db_path).replace("\\", "/")
        os.environ["DATABASE_URL"] = f"sqlite:///{_absolute_db_path_str}"
        print(f"[mcp] Converted database path to absolute: {_absolute_db_path_str}")

# ── Add project root to path ───────────────────────────────────────
sys.path.insert(0, str(PROJECT_ROOT))

# ── MCP SDK imports ─────────────────────────────────────────────────
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
import anyio
import json

# ── Import PLM tools ────────────────────────────────────────────────
# All tools execute through plm_tools.execute_tool, which enforces tenant
# isolation (deny-by-default) — never call TOOL_REGISTRY directly.
from app.plmassistant.plm_tools import execute_tool
from app.settings import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

# ── Tenant resolution ───────────────────────────────────────────────
# Tenant key for THIS MCP instance. Over stdio (local dev) it comes from the
# MCP_TENANT_KEY env var; a production HTTP transport resolves it per-request
# from the Authorization bearer. A missing key means the tools deny (they never
# run unscoped), so an unconfigured server cannot leak cross-tenant data.
_MCP_TENANT_KEY = os.environ.get("MCP_TENANT_KEY") or None

# ── MCP Server ──────────────────────────────────────────────────────
server = Server("plm-iq")


# ── Tool Definitions (MCP format) ──────────────────────────────────

PLM_TOOLS = [
    types.Tool(
        name="list_parts",
        description=(
            "List parts with optional filters and sorting. "
            "Use this for 'list parts', 'show latest parts', 'recent parts', "
            "or when the user wants to browse parts without a specific search query."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of parts to return (default: 10, max: 50)"},
                "status": {"type": "string", "enum": list(DEFAULT_SETTINGS["PART_STATUSES"]), "description": "Filter by status"},
                "sort": {"type": "string", "enum": ["created_date", "modified_date", "part_number"], "description": "Sort order"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_part",
        description="Look up a part by its part number and return all details (name, revision, material, status, dates).",
        inputSchema={
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "The part number to look up (e.g. BB-001, FRM-003)"},
            },
            "required": ["part_number"],
        },
    ),
    types.Tool(
        name="search_parts",
        description="Search for parts by name, number, or material. Use when the user isn't sure of the exact part number.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term — matches against part_number, part_name, and material"},
                "status": {"type": "string", "enum": list(DEFAULT_SETTINGS["PART_STATUSES"]), "description": "Optional status filter"},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="create_part",
        description="Create a new part based on a template part with optional field overrides. Auto-generates part number unless specified.",
        inputSchema={
            "type": "object",
            "properties": {
                "template_part": {"type": "string", "description": "The part number to use as a template (e.g. BB-001)"},
                "part_number": {"type": "string", "description": "Optional explicit part number (e.g. BB-010)"},
                "overrides": {"type": "object", "description": "Optional field overrides (part_name, material, status, uom, qty)"},
            },
            "required": ["template_part"],
        },
    ),
    types.Tool(
        name="update_part_status",
        description="Update the status of an existing part (DRAFT, RELEASED, or OBSOLETED).",
        inputSchema={
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "The part number to update (e.g. BB-001)"},
                "status": {"type": "string", "enum": list(DEFAULT_SETTINGS["PART_STATUSES"]), "description": "New status value"},
            },
            "required": ["part_number", "status"],
        },
    ),
    types.Tool(
        name="get_bom",
        description="Get the Bill of Materials for a part — shows all sub-components, quantities, and assembly structure.",
        inputSchema={
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "The part number to look up the BOM for (e.g. BB-001)"},
                "bom_type": {"type": "string", "enum": list(DEFAULT_SETTINGS["BOM_TYPES"]), "description": "Optional BOM type filter"},
            },
            "required": ["part_number"],
        },
    ),
    types.Tool(
        name="get_costing",
        description="Get costing details for a part — material cost, labor cost, overhead, machining, unit cost, and rolled total.",
        inputSchema={
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "The part number to look up costing for (e.g. BB-001)"},
            },
            "required": ["part_number"],
        },
    ),
    types.Tool(
        name="get_eco",
        description="Look up an Engineering Change Order by its ECO number. Returns title, description, status, affected part, change type.",
        inputSchema={
            "type": "object",
            "properties": {
                "eco_number": {"type": "string", "description": "The ECO number to look up (e.g. ECO-001)"},
            },
            "required": ["eco_number"],
        },
    ),
    types.Tool(
        name="search_ecos",
        description="Search Engineering Change Orders by part number or status. Use when asked about changes affecting a part.",
        inputSchema={
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "Optional part number to find ECOs affecting this part"},
                "status": {"type": "string", "enum": list(DEFAULT_SETTINGS["ECO_STATUSES"]), "description": "Optional status filter"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_aml",
        description="Get the Approved Manufacturer List for a part — manufacturers with lead times, costs, and quality ratings.",
        inputSchema={
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "The part number to look up approved manufacturers for"},
                "preferred_only": {"type": "boolean", "description": "If true, only return preferred manufacturers"},
            },
            "required": ["part_number"],
        },
    ),
    types.Tool(
        name="get_avl",
        description="Get the Approved Vendor List for a part — vendors with pricing, lead times, MOQ, ISO certification.",
        inputSchema={
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "The part number to look up approved vendors for"},
                "preferred_only": {"type": "boolean", "description": "If true, only return preferred vendors"},
            },
            "required": ["part_number"],
        },
    ),
    types.Tool(
        name="get_cad",
        description="Get CAD file metadata for a part — file names, formats (SLDASM, STEP, DWG, PDF), CAD system, modeling author.",
        inputSchema={
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "The part number to look up CAD files for"},
            },
            "required": ["part_number"],
        },
    ),
]


# ── MCP Handlers ────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the list of available PLM tools."""
    return PLM_TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[types.TextContent]:
    """Execute a PLM tool by name with the given arguments (tenant-scoped)."""
    logger.info(f"[mcp] Tool call: {name}({arguments})")

    try:
        # Parse arguments if they're a string
        if isinstance(arguments, str):
            arguments = json.loads(arguments) if isinstance(arguments, str) else arguments

        # execute_tool applies deny-by-default tenant isolation; a missing
        # MCP_TENANT_KEY yields a generic "access denied", never a cross-tenant
        # read or write.
        result = execute_tool(name, arguments, tenant_key=_MCP_TENANT_KEY)

        return [types.TextContent(type="text", text=result)]
    except Exception as e:
        logger.exception(f"[mcp] Tool execution failed: {e}")
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


# ── Server Entry Point ─────────────────────────────────────────────

async def main():
    """Run the MCP server in stdio mode."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    anyio.run(main)

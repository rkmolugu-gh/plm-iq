"""PLM Assistant Agent — ReAct loop with tool calling and multimodal support.

The agent follows the ReAct pattern:
  Thought → Action (tool call) → Observation (result) → Answer

Key features:
  - Tool-calling loop across all PLM entities (parts, BOM, costing, ECO, AML, AVL, CAD)
  - Multimodal vision support (images via aisearch/vision.py)
  - Conversation history management
  - Capped iterations to prevent infinite loops
"""

from __future__ import annotations

import json
import logging

from app.aisearch.llm_client import chat_with_tools
from app.aisearch.vision import vision_chat

from .config import ASSISTANT_MODEL, VISION_MODEL, MAX_TOOL_ROUNDS
from .plm_tools import ALL_TOOLS, execute_tool

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a helpful Assistant with access to comprehensive PLM tools.
Your job is to answer questions about parts, BOMs, costs, engineering changes,
manufacturers, vendors, CAD files, and spec documents.

You have access to the following tools — call them as needed to gather information:

PART TOOLS:
- list_parts(limit?, status?, sort?): List parts with optional filters. Use this for "list parts", "show latest parts", "recent parts".
- search_parts(query, status?): Search for parts by name, number, or material. Use when the user isn't sure of the exact part number.
- get_part(part_number): Look up a part's full details including revision, material, status, and dates.
- create_part(template_part, part_number?, overrides?): Create a new part based on a template. Auto-generates the next part number (e.g. BB-001 -> BB-007).
- update_part_status(part_number, status): Update a part's status to DRAFT, RELEASED, or OBSOLETED.

BOM TOOL:
- get_bom(part_number, bom_type?): Get the Bill of Materials showing all sub-components, quantities, and assembly levels.

COSTING TOOL:
- get_costing(part_number): Get material cost, labor cost, overhead, machining, unit cost, and rolled total for a part.

ECO TOOLS:
- get_eco(eco_number): Look up an Engineering Change Order by its ECO number.
- search_ecos(part_number?, status?): Find ECOs affecting a specific part or filter by status.

SUPPLIER TOOLS:
- get_aml(part_number, preferred_only?): Get approved manufacturers for a part, including lead times, costs, and quality ratings.
- get_avl(part_number, preferred_only?): Get approved vendors for a part, including pricing, MOQ, ISO cert, and payment terms.

CAD TOOL:
- get_cad(part_number): Get CAD file metadata including file formats, systems, and drawing numbers.

EFFICIENCY RULES (IMPORTANT):
- Be efficient: minimize tool calls. Only call tools when you lack specific information.
- If list_parts or search_parts returns enough information to answer the user's question, ANSWER DIRECTLY. Do NOT call get_part for each result.
- For "list latest parts" or "show recent parts", use list_parts with sort="modified_date" — do NOT search then get_part each result.
- For "get part X" where X is a specific part number, use get_part directly — do NOT search first.
- Think step-by-step but act efficiently: what is the MINIMUM set of tool calls needed?

GENERAL RULES:
- Answer ONLY using the data from your tool calls. If you don't have enough information, say so.
- For part numbers, always include the full part number (e.g. BB-001, not just BB).
- When listing costs, include currency values.
- Be concise and factual — use bullet points when listing multiple items.
- If the user greets you or asks a general question, answer conversationally.
- When a user asks to create or modify something, use the appropriate tool.

EXAMPLE (efficient tool use):
User: "list the latest 3 parts"
→ Call list_parts(limit=3, sort="modified_date")
→ Answer with the results directly (no get_part calls)

EXAMPLE (inefficient — avoid this):
User: "list the latest 3 parts"
→ Call search_parts("")  ❌
→ Call get_part("BB-001") ❌
→ Call get_part("BB-002") ❌
→ Call get_part("BB-003") ❌
→ Answer (too many calls!)"""


def _run_tool_loop(messages: list[dict], tenant_key: str | None = None) -> str:
    """Run the ReAct tool-calling loop.

    Sends messages to the LLM, executes any tool calls, feeds results back,
    and repeats until the LLM produces a final text response.

    Args:
        messages: The conversation messages to process.
        tenant_key: Optional tenant key for multi-tenant data isolation.

    Returns:
        The final assistant reply text.
    """
    tool_messages = list(messages)
    llm_response_text = ""

    for _round in range(MAX_TOOL_ROUNDS):
        response = chat_with_tools(tool_messages, tools=ALL_TOOLS, model=ASSISTANT_MODEL)
        llm_response_text = response.get("content") or ""
        tool_calls = response.get("tool_calls")

        if not tool_calls:
            break  # Final answer — no more tool calls needed

        # Append assistant message with tool calls
        tool_messages.append({"role": "assistant", "tool_calls": tool_calls})

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            try:
                arguments = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                arguments = {}

            logger.info(f"[assistant] Tool call: {tool_name}({arguments})")
            tool_result = execute_tool(tool_name, arguments, tenant_key=tenant_key)

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })
    else:
        logger.warning(f"Tool loop exceeded {MAX_TOOL_ROUNDS} rounds — using last response")

    return llm_response_text or "I processed your request."


def assistant_chat(
    *,
    messages: list[dict],
    system_prompt: str | None = None,
    model: str | None = None,
    tenant_key: str | None = None,
) -> str:
    """Process a conversation through the PLM Assistant agent.

    If the latest user message contains images (multimodal content), the
    vision_chat path is used instead of tool calling (many vision models
    don't support function calling + images in the same request).

    Args:
        messages: Full conversation history including the latest user message.
        system_prompt: Optional system prompt override (defaults to the PLM assistant prompt).
        model: Optional model override (defaults to ASSISTANT_MODEL).
        tenant_key: Optional tenant key for multi-tenant data isolation.

    Returns:
        The assistant's text response.
    """
    model = model or ASSISTANT_MODEL
    vision_model = VISION_MODEL or model
    system = system_prompt or _SYSTEM_PROMPT

    # Detect if the last user message has multimodal content (images)
    last_user = None
    for msg in reversed(messages):
        if msg["role"] == "user":
            last_user = msg
            break

    has_images = False
    uploaded_files = []
    if last_user and isinstance(last_user.get("content"), list):
        for part in last_user["content"]:
            if isinstance(part, dict) and part.get("type") == "image_url":
                has_images = True
            elif isinstance(part, dict) and part.get("type") == "text":
                uploaded_files.append(part)

    if has_images:
        # ── Vision path (no tool calling) ──────────────────────
        logger.info("[assistant] Using vision path (multimodal content detected)")
        logger.info(
            "[assistant] Model selection: assistant_model=%s vision_model=%s",
            model,
            vision_model,
        )

        # Build conversation history text
        history_parts = []
        for msg in messages[:-1]:  # all but last
            if msg["role"] == "user":
                c = msg.get("content", "")
                if isinstance(c, list):
                    texts = [p["text"] for p in c if isinstance(p, dict) and p.get("type") == "text"]
                    c = " ".join(texts)
                history_parts.append(f"User: {c}")
            elif msg["role"] == "assistant":
                history_parts.append(f"Assistant: {msg.get('content', '')}")

        vision_user = ""
        if history_parts:
            vision_user = "## Conversation History\n" + "\n\n".join(history_parts) + "\n\n"
        vision_user += "## Question\n" + (last_user.get("display_text", "") or "")

        # Collect images from the last user message
        images = []
        for part in last_user["content"]:
            if isinstance(part, dict) and part.get("type") == "image_url":
                images.append({
                    "base64_data": part["image_url"]["url"],
                    "mime_type": "image/png",  # best-effort; vision_chat uses it for display
                })

        reply = vision_chat(
            system_prompt=system,
            user_message=vision_user or "Describe the attached image(s).",
            images=images,
            model=vision_model,
            max_tokens=4096,
        )
        return reply

    # ── Tool-calling path (text only) ─────────────────────────
    logger.info("[assistant] Using tool-calling path")
    llm_messages = [{"role": "system", "content": system}]

    # Add conversation history
    for msg in messages[:-1]:
        if msg["role"] == "user":
            c = msg.get("content", "")
            if isinstance(c, list):
                texts = [p["text"] for p in c if isinstance(p, dict) and p.get("type") == "text"]
                c = " ".join(texts)
            llm_messages.append({"role": "user", "content": c})
        elif msg["role"] == "assistant":
            llm_messages.append({"role": "assistant", "content": msg.get("content", "")})

    # Add the latest user message (text only for tool calling)
    if last_user:
        c = last_user.get("content", "")
        if isinstance(c, list):
            texts = [p["text"] for p in c if isinstance(p, dict) and p.get("type") == "text"]
            c = " ".join(texts)
        llm_messages.append({"role": "user", "content": c})

    return _run_tool_loop(llm_messages, tenant_key=tenant_key)


def prepare_assistant_messages(
    message: str,
    uploaded_file_metas: list[dict],
) -> list | str:
    """Build the LLM content param — plain string if no images, else content array.

    Matches the OpenAI-compatible multimodal message format.
    """
    if not uploaded_file_metas:
        return message

    parts = []
    if message:
        parts.append({"type": "text", "text": message})

    for f in uploaded_file_metas:
        if f["type_hint"] == "image" and "base64_data" in f:
            parts.append({
                "type": "image_url",
                "image_url": {"url": f["base64_data"]},
            })
        elif f["type_hint"] in ("pdf", "text"):
            parts.append({"type": "text", "text": f"--- {f['filename']} ---\n{f['content']}"})
        else:
            parts.append({"type": "text", "text": f["content"]})

    return parts

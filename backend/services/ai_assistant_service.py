"""AIAssistantService - OpenRouter-backed workspace assistant with tools.

The seam where a real model plugs in. It talks to a provider (OpenRouter today)
through ``LLMProviderService`` and drives a ReAct tool-calling loop:

    Thought → Action (tool call) → Observation (result) → Answer

Design notes
------------
* OOP singleton (``assistant``) like the other services. Dependencies - the LLM
  provider and the tool service - are injected via ``__init__`` (defaults to the
  pinned ``llm`` / ``tools`` singletons), so swapping either needs no change here.
* ``respond`` is the single public method the gateway calls. It takes the
  per-tenant ``model``/``base_url`` (resolved from the ``setting`` blob) plus an
  optional ``identity`` carrying the auth context. Swapping providers later means
  changing only ``llm_provider_service``.
* A system prompt teaches the model what tools exist and to act efficiently
  (the pattern from the earlier ``assistant_agent.py`` reference).
* The tool loop is capped (``MAX_TOOL_ROUNDS``) to prevent runaway generations.
  Tool calls run inside one tenant-scoped RLS session so every statement is
  isolated to the signed-in tenant.
* When ``OPENROUTER_API_KEY`` is missing the response carries a ``warning`` the
  UI surfaces to the user.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime as dt
from typing import Any
from uuid import UUID

from .db import tenant_session
from .llm_provider_service import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    OPENROUTER_API_KEY_ENV,
    llm as default_llm,
)
from .tools_service import TOOL_SCHEMAS, tools as default_tools

logger = logging.getLogger(__name__)

#: Hard cap on ReAct iterations so a confused model can't loop forever.
MAX_TOOL_ROUNDS = 5

_NO_KEY_WARNING = (
    "OPENROUTER_API_KEY is not set. Set it in the environment (or setup/.env) "
    "so the assistant can reach the LLM. Until then it cannot answer."
)

_SYSTEM_PROMPT = """You are the PLM-IQ workspace Assistant with access to live tools.

Your job is to answer questions about the tenant's documents and other PLM
entities, and to help the user discover and act on workspace data.

You have access to the following tools - call them as needed to gather or act
on information:

TOOLS:
- list_documents(limit?): List the most recently created documents in this
  tenant, returning each document's id, prefix-number, revision, kind, name,
  lifecycle state, and description. Use this to discover documents before a
  follow-up question (e.g. open, edit, or ask about a specific one).

EFFICIENCY RULES (IMPORTANT):
- Be efficient: minimize tool calls. Only call a tool when you lack the specific
  information needed to answer.
- If list_documents already returns enough to answer, ANSWER DIRECTLY - do not
  call it again.
- Think step-by-step but act efficiently: what is the MINIMUM set of tool calls
  needed?
- Cap yourself at a few tool calls; if you cannot satisfy the request, say so.

GENERAL RULES:
- Answer ONLY using data from your tool calls or the conversation. If you don't
  have enough information, say so plainly.
- Be concise and factual - use bullet points when listing multiple items.
- If the user greets you or asks a general question, answer conversationally
  without calling tools."""


class AIAssistantService:
    """Connects to an LLM and drives the ReAct tool-calling loop."""

    #: Shown as the assistant's first message when the chat opens (fallback).
    greeting: str = (
        "PLM-IQ Assistant. I connect to an LLM via OpenRouter using the "
        "workspace's configured model and provider URL. Ask me anything."
    )

    def build_greeting(self, identity: Any = None) -> str:
        """Personalized opening line using the signed-in user's context.

        ``identity`` may be any object exposing ``full_name``, ``role_label``
        and ``tenant_id`` (the gateway's auth.Identity). Missing fields degrade
        gracefully to the generic greeting.
        """
        if not identity:
            return self.greeting
        name = getattr(identity, "full_name", "") or "there"
        role = getattr(identity, "role_label", "") or "user"
        tenant = getattr(identity, "tenant_id", "") or ""
        return (
            f"Hello {name} ({role}) from tenant {tenant}. "
            f"I am your PLM-IQ Assistant, connected via OpenRouter using the "
            f"workspace's configured model and provider URL. Ask me anything."
        )

    def __init__(self, tool_service: Any = None, llm_service: Any = None, *, identity: Any = None) -> None:
        """Initialize the assistant with optional tool/LLM service injection and auth context.

        Args:
            tool_service: Tool service instance. If not provided, uses the
                         default pinned singleton.
            llm_service: LLM provider instance. If not provided, uses the
                         default pinned singleton (OpenRouter today).
            identity: Optional identity object (tenant/subject info) used for
                      tool operations that require authentication context.
        """
        self.tools = tool_service or default_tools
        self.llm = llm_service or default_llm
        self.identity = identity

    def respond(
        self,
        message: str,
        *,
        history: list[dict[str, Any]] | None = None,
        tenant: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        identity: Any = None,
    ) -> dict[str, Any]:
        """Produce an assistant reply, running the ReAct tool loop when needed.

        Returns the stable contract (reply / model / created_at / history) plus a
        ``warning`` field whenever the call could not be completed (missing key or
        network/API failure) so the UI can alert the user.
        """
        # Store identity temporarily for tool access during this call.
        prior_identity = self.identity
        if identity is not None:
            self.identity = identity

        try:
            text = (message or "").strip()
            api_key = os.getenv(OPENROUTER_API_KEY_ENV)
            model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
            base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL

            if not api_key:
                logger.warning("ai_assistant.no_api_key", extra={"tenant": tenant or ""})
                return self._wrap(text, history, _NO_KEY_WARNING, model, base_url, live=False)

            # Resolve the tenant that scopes tool execution (RLS).
            tenant_id = getattr(self.identity, "tenant_id", None) if self.identity else tenant
            if not tenant_id:
                warning = "No tenant context is available, so I can't reach workspace tools."
                logger.warning("ai_assistant.no_tenant", extra={"tenant": tenant or ""})
                return self._wrap(text, history, warning, model, base_url, live=False)

            tid = UUID(str(tenant_id))
            conversation = self._build_conversation(text, history)

            try:
                with tenant_session(tid) as session:
                    reply, p_tok, c_tok, t_tok = self._run_tool_loop(
                        conversation, model, base_url, api_key, session, tid
                    )
                return self._wrap(
                    text, history, None, model, base_url, live=True,
                    reply=reply, prompt_tokens=p_tok,
                    completion_tokens=c_tok, total_tokens=t_tok,
                )
            except Exception as exc:  # noqa: BLE001 - surface a user-friendly warning
                warning = f"Could not reach the LLM at {base_url} (model {model}): {exc}"
                logger.warning("ai_assistant.llm_error", extra={"tenant": str(tid), "error": str(exc)})
                return self._wrap(text, history, warning, model, base_url, live=False)
        finally:
            # Restore prior identity (the singleton is shared across requests).
            self.identity = prior_identity

    def list_documents(
        self,
        session: object,
        tenant_id: UUID,
        *,
        limit: int = 5,
    ) -> dict[str, Any]:
        """List the last N documents in the tenant via the injected tool service.

        Delegates to ``self.tools.list_documents``; the tool service holds the
        actual DB query. If ``self.identity`` has a tenant_id it takes precedence.
        """
        effective_tenant = self.identity.tenant_id if self.identity else tenant_id
        return self.tools.list_documents(session, effective_tenant, limit=limit)

    # ── ReAct loop ──────────────────────────────────────────────────────────

    def _build_conversation(
        self, text: str, history: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        """Flatten history + the new user message into chat messages.

        System prompt is prepended per LLM call inside ``_run_tool_loop`` so it
        is always present even after tool-result messages are appended.
        """
        conversation: list[dict[str, Any]] = []
        for m in (history or []):
            role = m.get("role")
            if role in ("user", "assistant"):
                conversation.append({"role": role, "content": str(m.get("content", ""))})
        conversation.append({"role": "user", "content": text})
        return conversation

    def _run_tool_loop(
        self,
        conversation: list[dict[str, Any]],
        model: str,
        base_url: str,
        api_key: str,
        session: object,
        tenant_id: UUID,
    ) -> tuple[str, int, int, int]:
        """Run Thought → Action → Observation until a final answer.

        Returns (reply_text, total_prompt_tokens, total_completion_tokens,
        total_tokens) accumulated across all rounds.
        """
        prompt_tok = completion_tok = total_tok = 0
        conv = list(conversation)
        full = [{"role": "system", "content": _SYSTEM_PROMPT}, *conv]

        for _round in range(MAX_TOOL_ROUNDS):
            reply_text, tool_calls, p, c, t = self.llm.complete(
                api_key, model, base_url, full, tools=TOOL_SCHEMAS
            )
            prompt_tok += p or 0
            completion_tok += c or 0
            total_tok += t or 0

            if not tool_calls:
                return reply_text or "I processed your request.", prompt_tok, completion_tok, total_tok

            # Feed the assistant's tool calls back into the conversation.
            conv.append({"role": "assistant", "content": reply_text, "tool_calls": tool_calls})
            full.append({"role": "assistant", "content": reply_text, "tool_calls": tool_calls})

            for tc in tool_calls:
                name = (tc.get("function") or {}).get("name")
                try:
                    args = json.loads((tc.get("function") or {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                logger.info("ai_assistant.tool_call", extra={"tool": name, "args": args, "tenant": str(tenant_id)})
                result = self.tools.execute(name, args, session=session, tenant_id=tenant_id)
                tool_msg = {"role": "tool", "tool_call_id": tc.get("id"), "content": result}
                conv.append(tool_msg)
                full.append(tool_msg)

        logger.warning("ai_assistant.tool_loop_exhausted", extra={"rounds": MAX_TOOL_ROUNDS, "tenant": str(tenant_id)})
        return (
            "I reached the limit of tool calls without a final answer. "
            "Could you rephrase or narrow your request?",
            prompt_tok, completion_tok, total_tok,
        )

    def _wrap(
        self,
        text: str,
        history: list[dict[str, Any]] | None,
        warning: str | None,
        model: str,
        base_url: str,
        *,
        live: bool,
        reply: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> dict[str, Any]:
        if reply is None:
            reply = (
                "The assistant is not connected to an LLM. "
                + (warning or "Configure OPENROUTER_API_KEY to enable live answers.")
            )
        return {
            "reply": reply,
            "model": ("openrouter:" + model) if live else "unavailable",
            "connected": live,
            "model_used": model,
            "url_used": base_url,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "warning": warning,
            "created_at": dt.utcnow().isoformat() + "Z",
            "history": [
                *(history or []),
                {"role": "user", "content": text},
                {"role": "assistant", "content": reply},
            ],
        }


#: Pinned singleton used by the gateway.
assistant = AIAssistantService()

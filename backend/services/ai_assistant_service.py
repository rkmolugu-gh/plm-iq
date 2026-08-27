"""AIAssistantService - OpenRouter-backed workspace assistant.

The seam where a real model plugs in. It now talks to OpenRouter
(https://openrouter.ai) using two pieces of configuration:

* ``chatllmmodel``   - the model id (e.g. ``openai/gpt-4o-mini``), resolved from
                        the tenant's effective ``setting`` blob.
* ``llmproviderurl`` - the OpenRouter base URL (``https://openrouter.ai/api/v1``).
* ``OPENROUTER_API_KEY`` - read from the environment; REQUIRED. Without it the
   assistant degrades to a clear warning instead of failing silently.

Design notes
------------
* Stateless singleton (``assistant``) like the other services - no session or
  config is kept on ``self``; the route supplies the per-tenant model/url.
* ``respond`` is the single public method the gateway calls. Its signature takes
  the resolved ``model``/``base_url`` so swapping providers later means changing
  only this module (and the setting keys).
* Every call tests connectivity by performing a real chat completion; the model
  and URL used are logged and printed so it is obvious what was reached.
* When ``OPENROUTER_API_KEY`` is missing the response carries a ``warning`` the
  UI surfaces to the user.
* Tool service is injected for assistant-tooling capabilities.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from .llm_provider_service import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    OPENROUTER_API_KEY_ENV,
    llm as default_llm,
)
from .tools_service import tools as default_tools

logger = logging.getLogger(__name__)

_NO_KEY_WARNING = (
    "OPENROUTER_API_KEY is not set. Set it in the environment (or setup/.env) "
    "so the assistant can reach the LLM. Until then it cannot answer."
)


class AIAssistantService:
    """Connects to OpenRouter for live assistant replies."""

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
        """Produce an assistant reply via OpenRouter.

        Returns the stable contract (reply / model / created_at / history) plus a
        ``warning`` field whenever the call could not be completed (missing key or
        network/API failure) so the UI can alert the user.
        """
        # Store identity temporarily for tool access during this call
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

            try:
                reply, prompt_tokens, completion_tokens, total_tokens = self.llm.complete(api_key, model, base_url, text, history)
                return self._wrap(text, history, None, model, base_url, live=True, reply=reply, 
                               prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens)
            except Exception as exc:  # noqa: BLE001 - surface a user-friendly warning
                warning = f"Could not reach the LLM at {base_url} (model {model}): {exc}"
                logger.warning("ai_assistant.llm_error", extra={"tenant": tenant or "", "error": str(exc)})
                return self._wrap(text, history, warning, model, base_url, live=False)
        finally:
            # Restore prior identity
            self.identity = prior_identity

    def list_documents(
        self,
        session: Session,
        tenant_id: UUID,
        *,
        limit: int = 5,
    ) -> dict[str, Any]:
        """List the last N documents in the tenant via the injected tool service.

        Delegates to ``self.tools.list_documents``; the tool service holds the
        actual DB query. The assistant surface here is the public contract the
        route (or future LLM tool-call) calls.

        If ``self.identity`` has a tenant_id it will be used instead of the
        explicit ``tenant_id`` parameter for convenience when called from routes
        that already have the identity available.
        """
        effective_tenant = self.identity.tenant_id if self.identity else tenant_id
        return self.tools.list_documents(session, effective_tenant, limit=limit)

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

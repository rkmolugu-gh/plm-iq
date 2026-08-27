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
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime as dt
from typing import Any

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_NO_KEY_WARNING = (
    "OPENROUTER_API_KEY is not set. Set it in the environment (or setup/.env) "
    "so the assistant can reach the LLM. Until then it cannot answer."
)


class AIAssistantService:
    """Connects to OpenRouter for live assistant replies."""

    #: Shown as the assistant's first message when the chat opens.
    greeting: str = (
        "PLM-IQ Assistant. I connect to an LLM via OpenRouter using the "
        "workspace's configured model and provider URL. Ask me anything."
    )

    def respond(
        self,
        message: str,
        *,
        history: list[dict[str, Any]] | None = None,
        tenant: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        """Produce an assistant reply via OpenRouter.

        Returns the stable contract (reply / model / created_at / history) plus a
        ``warning`` field whenever the call could not be completed (missing key or
        network/API failure) so the UI can alert the user.
        """
        text = (message or "").strip()
        api_key = os.getenv(OPENROUTER_API_KEY_ENV)
        model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL

        if not api_key:
            logger.warning("ai_assistant.no_api_key", extra={"tenant": tenant or ""})
            return self._wrap(text, history, _NO_KEY_WARNING, model, base_url, live=False)

        try:
            reply = self._call_openrouter(api_key, model, base_url, text, history)
            return self._wrap(text, history, None, model, base_url, live=True, reply=reply)
        except Exception as exc:  # noqa: BLE001 - surface a user-friendly warning
            warning = f"Could not reach the LLM at {base_url} (model {model}): {exc}"
            logger.warning("ai_assistant.llm_error", extra={"tenant": tenant or "", "error": str(exc)})
            return self._wrap(text, history, warning, model, base_url, live=False)

    def _call_openrouter(
        self,
        api_key: str,
        model: str,
        base_url: str,
        text: str,
        history: list[dict[str, Any]] | None,
    ) -> str:
        """Perform one chat completion and return the assistant text."""
        messages = [
            {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
            for m in (history or [])
            if str(m.get("content", "")).strip()
        ]
        messages.append({"role": "user", "content": text})

        url = f"{base_url}/chat/completions"
        payload = json.dumps(
            {"model": model, "messages": messages, "stream": False}
        ).encode("utf-8")

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("HTTP-Referer", "https://plm-iq.local")
        req.add_header("X-Title", "PLM-IQ Assistant")

        # Surface exactly what we connected to for visibility/debugging.
        print(f"[AI Assistant] Connecting to LLM -> model={model} url={base_url}")
        logger.info("ai_assistant.llm_connect", extra={"model": model, "url": base_url})

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

        return data["choices"][0]["message"]["content"]

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

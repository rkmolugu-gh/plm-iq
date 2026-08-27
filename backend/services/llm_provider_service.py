"""LLMProviderService - the single seam for talking to an LLM backend.

This module isolates every provider-specific detail (auth header shape, URL
construction, request/response parsing, token extraction, tool-call parsing)
behind one interface. Today it speaks OpenRouter (OpenAI-compatible tool
calling); tomorrow swapping to Anthropic, Azure, Ollama, or a self-hosted
endpoint means editing ONLY this file - the assistant and gateway never learn
which provider answered.

Contract
--------
* ``complete(api_key, model, base_url, messages, tools=None)`` is the single
  public method the assistant calls. It returns
  ``(reply_text, tool_calls, prompt_tokens, completion_tokens, total_tokens)``
  so the caller stays provider-agnostic.
  - ``messages`` is the full evolving chat array (system/user/assistant/tool).
  - ``tools`` is an optional list of OpenAI-style function schemas; when given,
    the provider requests tool calls and parses them out of the response.
  - ``tool_calls`` is ``[]`` when the model answers directly, otherwise a list
    of ``{"id", "function": {"name", "arguments"}}``.
* ``DEFAULT_MODEL`` / ``DEFAULT_BASE_URL`` are provider defaults, overridable
  per tenant via the ``setting`` blob (``chatllmmodel`` / ``llmproviderurl``).
* ``OPENROUTER_API_KEY_ENV`` is the env var the runtime must set; a missing key
  is a hard error surfaced by the caller, not a silent failure.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class LLMProviderService:
    """Provider-agnostic chat-completion client (OpenRouter today)."""

    def complete(
        self,
        api_key: str,
        model: str,
        base_url: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[dict[str, Any]], int | None, int | None, int | None]:
        """One chat completion. Returns (reply_text, tool_calls, prompt, completion, total).

        Provider-specific logic lives entirely here. The assistant receives a
        plain tuple and never inspects the wire format.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            # Instruct the model to use them when helpful.
            payload["tool_choice"] = "auto"

        url = f"{base_url.rstrip('/')}/chat/completions"
        body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("HTTP-Referer", "https://plm-iq.local")
        req.add_header("X-Title", "PLM-IQ Assistant")

        # Surface exactly what we connected to for visibility/debugging.
        print(f"[AI Assistant] Connecting to LLM -> model={model} url={base_url} tools={bool(tools)}")
        logger.info("ai_assistant.llm_connect", extra={"model": model, "url": base_url, "tools": bool(tools)})

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")

        choice = data["choices"][0]["message"]
        reply_text = choice.get("content") or ""
        raw_tool_calls = choice.get("tool_calls") or []
        tool_calls = [
            {
                "id": tc.get("id"),
                "function": {
                    "name": tc.get("function", {}).get("name"),
                    "arguments": tc.get("function", {}).get("arguments") or "{}",
                },
            }
            for tc in raw_tool_calls
        ]
        return reply_text, tool_calls, prompt_tokens, completion_tokens, total_tokens


#: Pinned singleton used by the assistant.
llm = LLMProviderService()

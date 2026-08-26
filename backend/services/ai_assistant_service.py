"""AIAssistantService - placeholder chatbot behind the workspace AI menu.

This is the seam where a real model/agent will eventually plug in. For now it
returns deterministic dummy replies so the chat UI, the page route, and the JSON
chat endpoint all have something to render end-to-end without a live backend.

Design notes
------------
* Stateless singleton (``assistant``) like the other services - no session or
  config is kept on ``self``.
* ``respond`` is the single public method the gateway calls. Its signature is
  intentionally model-shaped (message + optional history) so swapping in a real
  LLM later means changing only this module, not the route or the UI.
* History is unstructured (list of {"role", "content"}) so a future provider
  that wants prior turns can consume it as-is.
"""
from __future__ import annotations

import logging
from datetime import datetime as dt
from typing import Any

logger = logging.getLogger(__name__)

# Canned replies keyed by a substring match on the user's message, so the demo
# feels a little aware without any intelligence behind it.
_KEYED_REPLIES: tuple[tuple[str, str], ...] = (
    ("hello", "Hello! I'm the PLM-IQ assistant (demo mode). Ask me about items, documents, or changes."),
    ("hi", "Hi there! This assistant is running on placeholder responses for now."),
    ("document", "Documents are controlled vertices with file content and revisions. (Demo reply - no live data yet.)"),
    ("item", "Items and their revisions live on the shared graph core. (Demo reply - no live data yet.)"),
    ("change", "Change management and impact analysis are on the roadmap. (Demo reply.)"),
    ("help", "I'm a dummy assistant right now - my backend returns fixed values. Real answers come later."),
)


class AIAssistantService:
    """Returns placeholder chatbot replies. Replace ``respond`` with a real
    provider call to make the assistant live."""

    #: Shown as the assistant's first message when the chat opens.
    greeting: str = (
        "PLM-IQ Assistant (demo). I'm wired to a placeholder backend that "
        "returns dummy values - try sending a message."
    )

    def respond(
        self,
        message: str,
        *,
        history: list[dict[str, Any]] | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any]:
        """Produce a dummy assistant reply.

        Returns the same shape a real backend would: a reply string plus an
        echo of the history, so the UI has a stable contract to build on.
        """
        text = (message or "").strip()
        reply = self._dummy_reply(text)
        logger.info("ai_assistant.respond", extra={
            "tenant": tenant or "",
            "prompt_len": len(text),
            "history_turns": len(history or []),
        })
        return {
            "reply": reply,
            "model": "dummy",
            "created_at": dt.utcnow().isoformat() + "Z",
            "history": [
                *(history or []),
                {"role": "user", "content": text},
                {"role": "assistant", "content": reply},
            ],
        }

    def _dummy_reply(self, text: str) -> str:
        lowered = text.lower()
        for needle, canned in _KEYED_REPLIES:
            if needle in lowered:
                return canned
        if not text:
            return "I didn't catch that - type a question and I'll reply with a placeholder for now."
        return (
            f"(Demo) You said: \"{text}\". The AI backend isn't connected yet, "
            "so this is a dummy response. Real model answers will land here."
        )


#: Pinned singleton used by the gateway.
assistant = AIAssistantService()

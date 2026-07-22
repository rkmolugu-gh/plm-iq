"""LLM API client — embed text, chat, and vision chat with an OpenAI-compatible LLM API.

Summary:
    Provides embed() for generating vector embeddings (bge-m3, 1024-dim)
    and chat() for RAG answer generation (deepseek-v4-flash).
    Uses OpenAI-compatible request/response format.

    Tool calling:
        chat_with_tools() extends chat() by sending tool definitions to the LLM.
        If the LLM responds with a tool_call, the caller can execute the tool
        and send the result back for a final response.

    Vision:
        vision_chat() is re-exported from aisearch.vision for sending text +
        images to a vision-capable LLM. See aisearch/vision.py for details.
"""

import logging
import time
import requests
from typing import Optional

from aisearch.config import LLM_BASE_URL, LLM_API_KEY, EMBEDDING_MODEL, CHAT_MODEL

logger = logging.getLogger(__name__)


def _headers() -> dict:
    """Build standard headers with API key."""
    return {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }


def embed(text: str, model: Optional[str] = None, max_retries: int = 5) -> list[float]:
    """Generate embedding vector for the given text.

    Retries with exponential backoff on 429 (rate limit) errors.

    Args:
        text: Input text to embed.
        model: Model name (defaults to bge-m3).
        max_retries: Max retries on 429 rate limit errors (default 5).

    Returns:
        List of floats representing the embedding vector (1024-dim).

    Raises:
        RuntimeError: If the API call fails after all retries.
    """
    t0 = time.time()
    model = model or EMBEDDING_MODEL
    url = f"{LLM_BASE_URL}/embeddings"
    payload = {"input": text, "model": model}

    for attempt in range(1, max_retries + 1):
        logger.debug(f"Embedding {len(text)} chars with {model} (attempt {attempt})")
        resp = requests.post(url, headers=_headers(), json=payload, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data")
            if not items:
                raise RuntimeError(f"Embedding API returned empty data: {resp.text}")
            vector = items[0].get("embedding", [])
            usage = data.get("usage", {})
            logger.info(
                "Embedding: model=%s dims=%d chars=%d tokens=%s elapsed=%.2fs",
                model, len(vector), len(text),
                usage.get("total_tokens", "?"),
                time.time() - t0,
            )
            logger.debug(f"Got embedding: {len(vector)} dimensions")
            return vector

        if resp.status_code == 429 and attempt < max_retries:
            wait = min(2 ** attempt, 60)  # 2, 4, 8, 16, 32... capped at 60s
            logger.warning(f"Rate limited (429), retrying in {wait}s (attempt {attempt}/{max_retries})")
            time.sleep(wait)
        else:
            raise RuntimeError(f"Embedding API error {resp.status_code}: {resp.text}")

    raise RuntimeError(f"Embedding API failed after {max_retries} retries")


def chat(messages: list[dict], model: Optional[str] = None, max_retries: int = 5) -> str:
    """Send a chat completion request and return the assistant's reply.

    Retries with exponential backoff on 429 (rate limit) errors.

    Args:
        messages: List of dicts with 'role' and 'content' keys.
        model: Model name (defaults to deepseek-v4-flash).
        max_retries: Max retries on 429 rate limit errors (default 5).

    Returns:
        The assistant's text response.

    Raises:
        RuntimeError: If the API call fails after all retries.
    """
    t0 = time.time()
    model = model or CHAT_MODEL
    url = f"{LLM_BASE_URL}/chat/completions"
    payload = {"model": model, "messages": messages}

    for attempt in range(1, max_retries + 1):
        logger.debug(f"Chat: {len(messages)} messages with {model} (attempt {attempt})")
        resp = requests.post(url, headers=_headers(), json=payload, timeout=60)

        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices")
            if not choices:
                raise RuntimeError(f"Chat API returned empty choices: {resp.text}")
            reply = choices[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            logger.info(
                "Chat: model=%s reply=%d chars prompt=%s completion=%s total=%s elapsed=%.2fs",
                model, len(reply),
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
                usage.get("total_tokens", "?"),
                time.time() - t0,
            )
            logger.debug(f"Chat reply: {len(reply)} chars")
            return reply

        if resp.status_code == 429 and attempt < max_retries:
            wait = min(2 ** attempt, 60)
            logger.warning(f"Chat rate limited (429), retrying in {wait}s (attempt {attempt}/{max_retries})")
            time.sleep(wait)
        else:
            raise RuntimeError(f"Chat API error {resp.status_code}: {resp.text}")

    raise RuntimeError(f"Chat API failed after {max_retries} retries")


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: Optional[str] = None,
    max_retries: int = 5,
) -> dict:
    """Send a chat completion with tool definitions and return the full response.

    Retries with exponential backoff on 429 (rate limit) errors.

    The LLM may respond with either:
      - A text response (no tool call): {"role": "assistant", "content": "..."}
      - A tool call request: {"role": "assistant", "tool_calls": [...], "content": None}

    Args:
        messages: List of dicts with 'role' and 'content' keys.
        tools: List of tool definition dicts (OpenAI function-calling format).
        model: Model name (defaults to deepseek-v4-flash).
        max_retries: Max retries on 429 rate limit errors (default 5).

    Returns:
        The full response dict from the API, containing either 'content' or 'tool_calls'.

    Raises:
        RuntimeError: If the API call fails after all retries.
    """
    t0 = time.time()
    model = model or CHAT_MODEL
    url = f"{LLM_BASE_URL}/chat/completions"
    payload = {"model": model, "messages": messages, "tools": tools}

    for attempt in range(1, max_retries + 1):
        logger.debug(f"Chat with tools: {len(messages)} messages, {len(tools)} tools (attempt {attempt})")
        resp = requests.post(url, headers=_headers(), json=payload, timeout=60)

        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices")
            if not choices:
                raise RuntimeError(f"Chat API returned empty choices: {resp.text}")
            choice = choices[0].get("message", {})

            result = {"role": choice.get("role", "assistant")}
            if choice.get("content"):
                result["content"] = choice["content"]
            if choice.get("tool_calls"):
                result["tool_calls"] = choice["tool_calls"]

            usage = data.get("usage", {})
            logger.info(
                "ChatWithTools: model=%s tools=%d has_content=%s has_tool_calls=%s prompt=%s completion=%s total=%s elapsed=%.2fs",
                model, len(tools),
                bool(result.get("content")),
                bool(result.get("tool_calls")),
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
                usage.get("total_tokens", "?"),
                time.time() - t0,
            )

            logger.debug(f"Chat with tools reply: content={bool(result.get('content'))}, tool_calls={len(result.get('tool_calls', []))}")
            return result

        if resp.status_code == 429 and attempt < max_retries:
            wait = min(2 ** attempt, 60)
            logger.warning(f"Chat with tools rate limited (429), retrying in {wait}s (attempt {attempt}/{max_retries})")
            time.sleep(wait)
        else:
            raise RuntimeError(f"Chat API error {resp.status_code}: {resp.text}")

    raise RuntimeError(f"Chat API failed after {max_retries} retries")


# ── Vision re-exports ──────────────────────────────────────────────
# vision_chat and prepare_image are implemented in aisearch/vision.py
# (OpenAI SDK-based, with image resize / format conversion / base64).
# Re-exported here so callers can import everything from llm_client.

from aisearch.vision import vision_chat, prepare_image  # noqa: E402, F401

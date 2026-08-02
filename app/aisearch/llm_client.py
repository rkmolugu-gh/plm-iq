"""LLM API client — embed text, chat, and vision chat with an OpenAI-compatible LLM API.

Summary:
    Provides embed() for generating vector embeddings (bge-m3, 1024-dim)
    and chat() for RAG answer generation .
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

from .config import LLM_BASE_URL, LLM_API_KEY, EMBEDDING_MODEL, CHAT_MODEL

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


def _parse_error_message(resp: requests.Response) -> str:
    """Extract a human-readable error message from an API response.

    Tries to parse JSON error responses like:
      {"error": {"message": "...", "code": 502}}
      {"error": "..."}
      {"message": "..."}

    Falls back to the raw response text.
    """
    try:
        data = resp.json()
        # OpenRouter / Nvidia style: {"error": {"message": "...", "code": 502}}
        if isinstance(data.get("error"), dict):
            msg = data["error"].get("message", "")
            code = data["error"].get("code", resp.status_code)
            return f"{msg} (code: {code})"
        # Simple error: {"error": "..."}
        elif isinstance(data.get("error"), str):
            return data["error"]
        # Message style: {"message": "..."}
        elif isinstance(data.get("message"), str):
            return data["message"]
    except Exception:
        pass
    return resp.text[:200]


def chat(messages: list[dict], model: Optional[str] = None, max_retries: int = 5) -> str:
    """Send a chat completion request and return the assistant's reply.

    Retries with exponential backoff on 429 (rate limit) errors and on 502/503
    errors that contain rate-limit messages.

    Args:
        messages: List of dicts with 'role' and 'content' keys.
        model: Model name
        max_retries: Max retries on 429 rate limit errors (default 5).

    Returns:
        The assistant's text response.

    Raises:
        RuntimeError: If the API call fails after all retries.
            The error message will contain a user-friendly description.
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
                error_msg = _parse_error_message(resp)
                raise RuntimeError(f"Chat API returned empty choices: {error_msg}")
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

        # Check if this is a rate-limit error (429 or 502/503 with rate limit message)
        is_rate_limit = False
        error_msg = _parse_error_message(resp)

        if resp.status_code == 429:
            is_rate_limit = True
        elif resp.status_code in (502, 503):
            # Some providers return 502/503 for rate limits
            if any(keyword in error_msg.lower() for keyword in ["rate", "limit", "quota", "exhaust", "too many"]):
                is_rate_limit = True
                logger.warning(f"Chat: {resp.status_code} error appears to be rate-limit related: {error_msg}")

        if is_rate_limit and attempt < max_retries:
            wait = min(2 ** attempt, 60)
            logger.warning(f"Chat rate limited ({resp.status_code}), retrying in {wait}s (attempt {attempt}/{max_retries})")
            time.sleep(wait)
        else:
            # Provide a user-friendly error message
            if "rate" in error_msg.lower() and "limit" in error_msg.lower():
                raise RuntimeError(f"Rate limit reached: {error_msg}")
            elif resp.status_code >= 500:
                raise RuntimeError(f"LLM service error (HTTP {resp.status_code}): {error_msg}")
            else:
                raise RuntimeError(f"Chat API error (HTTP {resp.status_code}): {error_msg}")

    raise RuntimeError(f"Chat API failed after {max_retries} retries")


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: Optional[str] = None,
    max_retries: int = 5,
) -> dict:
    """Send a chat completion with tool definitions and return the full response.

    Retries with exponential backoff on 429 (rate limit) errors and on 502/503
    errors that contain rate-limit messages (some providers return 502 for rate limits).

    The LLM may respond with either:
      - A text response (no tool call): {"role": "assistant", "content": "..."}
      - A tool call request: {"role": "assistant", "tool_calls": [...], "content": None}

    Args:
        messages: List of dicts with 'role' and 'content' keys.
        tools: List of tool definition dicts (OpenAI function-calling format).
        model: Model name.
        max_retries: Max retries on 429 rate limit errors (default 5).

    Returns:
        The full response dict from the API, containing either 'content' or 'tool_calls'.

    Raises:
        RuntimeError: If the API call fails after all retries.
            The error message will contain a user-friendly description.
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
                error_msg = _parse_error_message(resp)
                raise RuntimeError(f"Chat API returned empty choices: {error_msg}")
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

        # Check if this is a rate-limit error (429 or 502/503 with rate limit message)
        is_rate_limit = False
        error_msg = _parse_error_message(resp)

        if resp.status_code == 429:
            is_rate_limit = True
        elif resp.status_code in (502, 503):
            # Some providers return 502/503 for rate limits
            if any(keyword in error_msg.lower() for keyword in ["rate", "limit", "quota", "exhaust", "too many"]):
                is_rate_limit = True
                logger.warning(f"Chat with tools: {resp.status_code} error appears to be rate-limit related: {error_msg}")

        if is_rate_limit and attempt < max_retries:
            wait = min(2 ** attempt, 60)
            logger.warning(f"Chat with tools rate limited ({resp.status_code}), retrying in {wait}s (attempt {attempt}/{max_retries})")
            time.sleep(wait)
        else:
            # Provide a user-friendly error message
            if "rate" in error_msg.lower() and "limit" in error_msg.lower():
                raise RuntimeError(f"Rate limit reached: {error_msg}")
            elif resp.status_code >= 500:
                raise RuntimeError(f"LLM service error (HTTP {resp.status_code}): {error_msg}")
            else:
                raise RuntimeError(f"Chat API error (HTTP {resp.status_code}): {error_msg}")

    raise RuntimeError(f"Chat API failed after {max_retries} retries")


# ── Vision re-exports ──────────────────────────────────────────────
# vision_chat and prepare_image are implemented in aisearch/vision.py
# (OpenAI SDK-based, with image resize / format conversion / base64).
# Re-exported here so callers can import everything from llm_client.

from .vision import vision_chat, prepare_image  # noqa: E402, F401

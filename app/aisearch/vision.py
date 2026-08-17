"""Multimodal vision module — process images and call vision-capable LLMs.

Summary:
    Provides image preparation (resize, format conversion, base64 encoding)
    and a vision_chat() function that sends text + images to any OpenAI-
    compatible vision LLM. Designed as a reusable module for assistant and
    search/rag workflows.

    Inspired by drawing_interpreter.py in the companion tool at
    C:\\ramesh2026\\repo-2026\\drawing-interpreter\\drawing_interpreter.py
    — adapted for sync FastAPI routes and modular reuse within aisearch/.

Usage:
    from aisearch.vision import prepare_image, vision_chat

    # Prepare an uploaded image
    image = prepare_image(raw_bytes, "photo.png")

    # Send to vision LLM
    reply = vision_chat(
        system_prompt="Describe this image.",
        user_message="What part is this?",
        images=[image],
    )
"""

from __future__ import annotations

import base64
import logging
import time
from io import BytesIO
from typing import Optional

from openai import (
    APIStatusError,
    OpenAI,
    RateLimitError,
    InternalServerError,
    APIConnectionError,
)
from PIL import Image, UnidentifiedImageError

from .config import (
    LLM_BASE_URL,
    LLM_API_KEY,
    CHAT_MODEL,
    VISION_MODEL,
    VISION_MAX_IMAGE_DIMENSION,
    VISION_MAX_TOKENS,
    VISION_TIMEOUT_SECONDS,
    MAX_UPLOAD_SIZE,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Tunables
# --------------------------------------------------------------------------- #

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"}
NATIVE_API_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}

DEFAULT_MAX_DIMENSION = 4096       # px on the longest side before downscale
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TIMEOUT_SECONDS = 180.0
MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 2.0

# Transient errors worth retrying (ordered check — RateLimitError and
# InternalServerError are subclasses of APIStatusError).
_RETRIABLE = (APIConnectionError, RateLimitError, InternalServerError)

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class VisionError(Exception):
    """Base for expected, user-facing errors raised by this module."""


class ImageValidationError(VisionError):
    """The provided bytes could not be decoded or exceed size limits."""


class VisionAPIError(VisionError):
    """The LLM API rejected the request or returned an empty response."""


# --------------------------------------------------------------------------- #
# Image preparation  (sync — called from FastAPI route handlers)
# --------------------------------------------------------------------------- #


def _decode_resize_encode(raw: bytes, max_dimension: int) -> tuple[bytes, str]:
    """Decode, optionally downscale, and re-encode an image.

    CPU-bound work: decodes the image, downscales if its longest side exceeds
    *max_dimension*, and re-encodes to a format the API can handle (PNG for
    non-JPEG sources, JPEG otherwise).

    Returns:
        (encoded_bytes, mime_type)
    """
    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except UnidentifiedImageError as exc:
        raise ImageValidationError("File isn't a decodable image.") from exc
    except Exception as exc:
        raise ImageValidationError(f"Could not read image data: {exc}") from exc

    fmt = (img.format or "").upper()
    needs_resize = max(img.size) > max_dimension
    if needs_resize:
        img = img.copy()
        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    if fmt in NATIVE_API_FORMATS and not needs_resize:
        mime = "image/jpeg" if fmt == "JPEG" else f"image/{fmt.lower()}"
        return raw, mime

    buf = BytesIO()
    if fmt == "JPEG":
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=90)
        mime = "image/jpeg"
    else:
        if img.mode not in ("RGB", "RGBA", "L", "P"):
            img = img.convert("RGBA")
        img.save(buf, format="PNG", optimize=True)
        mime = "image/png"

    return buf.getvalue(), mime


def prepare_image(
    raw: bytes,
    filename: str = "image",
    max_size_bytes: Optional[int] = None,
    max_dimension: int = DEFAULT_MAX_DIMENSION,
) -> dict:
    """Validate, normalize, and base64-encode image bytes for LLM vision API.

    Args:
        raw: Raw file bytes of the image.
        filename: Original filename (used for logging/error messages only).
        max_size_bytes: Maximum allowed payload **after** normalization.
                        Defaults to MAX_UPLOAD_SIZE from config.
        max_dimension: Longest side in px; images larger than this are downscaled.

    Returns:
        dict with keys:
            filename    — original filename
            mime_type   — e.g. ``"image/png"``
            base64_data — ``data:{mime};base64,{encoded}`` ready for LLM
            size_bytes  — final encoded size
            size_display — human-readable size string

    Raises:
        ImageValidationError if the file is not a valid image or exceeds size limits.
    """
    max_size_bytes = max_size_bytes or MAX_UPLOAD_SIZE
    raw_size = len(raw)
    logger.info("Preparing image %r (raw %.2f KB)...", filename, raw_size / 1024)

    processed, mime = _decode_resize_encode(raw, max_dimension)

    if len(processed) > max_size_bytes:
        raise ImageValidationError(
            f"Image {filename!r} is {len(processed) / (1024 * 1024):.1f} MB "
            f"after normalization, over the {max_size_bytes // (1024 * 1024)} MB limit."
        )

    b64 = base64.b64encode(processed).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"

    size_kb = len(processed) / 1024
    logger.info("Image %r prepared: %.1f KB, %s", filename, size_kb, mime)

    return {
        "filename": filename,
        "mime_type": mime,
        "base64_data": data_uri,
        "size_bytes": len(processed),
        "size_display": f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB",
    }


# --------------------------------------------------------------------------- #
# Vision LLM call  (sync, with retries, matches existing FastAPI route style)
# --------------------------------------------------------------------------- #


def _format_api_error(exc: APIStatusError) -> str:
    bits = [f"status {exc.status_code}"]
    if exc.code:
        bits.append(f"code={exc.code}")
    if exc.param:
        bits.append(f"param={exc.param}")
    return f"{exc.message} ({', '.join(bits)})"


def vision_chat(
    *,
    system_prompt: Optional[str] = None,
    user_message: str = "",
    images: list[dict] | None = None,
    model: Optional[str] = None,
    max_tokens: int = VISION_MAX_TOKENS,
    timeout: float = VISION_TIMEOUT_SECONDS,
    temperature: float = 0.7,
    tenant_key: Optional[str] = None,
) -> str:
    """Send a text + optional images to a vision-capable LLM.

    Uses the OpenAI-compatible endpoint configured in ``LLM_BASE_URL`` /
    ``LLM_API_KEY`` with a sync client. Retries transient errors (connection,
    429, 5xx) with exponential backoff.

    Args:
        system_prompt:   Optional system-level instruction.
        user_message:    The user's text prompt (may be empty if images are sent).
        images:          List of prepared image dicts from :func:`prepare_image`.
                         Each must have keys ``base64_data`` and ``mime_type``.
        model:           Model id override. Defaults to ``VISION_MODEL`` (then
                         ``CHAT_MODEL``) from config.
        max_tokens:      Max tokens in the response (default 2000).
        timeout:         Per-request timeout in seconds (default 180).
        temperature:     Sampling temperature (default 0.7).

    Returns:
        The model's text response.

    Raises:
        VisionAPIError if all retries are exhausted or the API rejects the request.
    """
    from .llm_client import _resolve as _resolve_cfg
    cfg = _resolve_cfg(tenant_key)
    model = model or cfg["vision_model"] or cfg["chat_model"] or (VISION_MODEL or CHAT_MODEL)
    if not model:
        raise VisionAPIError("CHAT_MODEL is not configured. Set it in the global settings (.env fallback).")

    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], timeout=timeout, max_retries=0)

    # Build content array
    content: list[dict] = []
    if user_message:
        content.append({"type": "text", "text": user_message})
    if images:
        for img in images:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": img["base64_data"],
                    "detail": "high",
                },
            })

    if not content:
        raise VisionAPIError("No text or images provided to vision_chat().")

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content})

    logger.info(
        "Vision chat: model=%s user_msg=%d chars images=%d",
        model, len(user_message), len(images or []),
    )

    t0 = time.time()
    try:
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False,
                )
                choice = resp.choices[0] if resp.choices else None
                if not choice or not choice.message.content:
                    raise VisionAPIError(
                        f"The model ({model!r}) returned an empty response — "
                        "it may not support image input. Try a vision-capable model."
                    )

                text = choice.message.content
                elapsed = time.time() - t0
                logger.info(
                    "Vision chat completed: reply=%d chars elapsed=%.2fs",
                    len(text), elapsed,
                )
                return text

            except _RETRIABLE as exc:
                if attempt >= MAX_RETRIES:
                    raise VisionAPIError(
                        f"Giving up after {attempt} attempt(s) calling the vision LLM: {exc}"
                    ) from exc
                backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Vision LLM call failed (%s: %s). Retrying in %.1fs (attempt %d/%d)...",
                    exc.__class__.__name__, exc, backoff, attempt, MAX_RETRIES,
                )
                time.sleep(backoff)

            except APIStatusError as exc:
                raise VisionAPIError(
                    f"LLM API rejected the request: {_format_api_error(exc)}\n"
                    "If this model doesn't accept image input, set CHAT_MODEL "
                    "in plm-iq/.env to a vision-capable model."
                ) from exc

    except VisionError:
        raise
    except Exception as exc:
        raise VisionAPIError(f"Unexpected error calling vision LLM: {exc}") from exc
    finally:
        client.close()

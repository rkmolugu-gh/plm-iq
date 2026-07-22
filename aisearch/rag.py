"""RAG engine — Retrieval Augmented Generation for PLM data.

Summary:
    Takes a user query, retrieves relevant context via hybrid search,
    then calls deepseek-v4-flash to generate a grounded answer with
    citations back to the source documents.

    Multimodal support:
        rag_answer_multimodal() extends rag_answer() with image support,
        using vision_chat() from aisearch.vision to send images alongside
        search context.

    Flow:
        query → hybrid_search() → context docs → build prompt → LLM → answer + citations
        query + image(s) → hybrid_search() → context docs → build prompt → vision LLM → answer + citations
"""

import logging
import time
from typing import Optional

from aisearch.search import hybrid_search
from aisearch.llm_client import chat, vision_chat, prepare_image
from aisearch.config import CHAT_MODEL, VISION_MODEL, RAG_MAX_CONTEXT_DOCS

logger = logging.getLogger(__name__)


_RAG_SYSTEM_PROMPT = """You are a helpful PLM (Product Lifecycle Management) data assistant.
Your job is to answer questions about parts, BOMs, costs, engineering changes,
manufacturers, vendors, CAD files, and spec documents.

Rules:
- Answer ONLY using the context provided below. If the context doesn't contain the answer, say "I don't have enough information to answer this."
- Cite your sources using [N] notation where N is the result number.
- Be concise and factual. Use bullet points when listing multiple items.
- If the question is about costs, include the currency values.
- For part numbers, always include the full part number."""


def rag_answer(query: str, entity_type: Optional[str] = None) -> dict:
    """Generate a RAG answer for the given query.

    Args:
        query: The user's natural language question.
        entity_type: Optional entity filter to narrow the search.

    Returns:
        dict with keys:
            answer:      The LLM-generated answer text.
            citations:   List of source documents used.
            results:     Full search results for display.
            timing:      Timing breakdown for observability.
    """
    t_start = time.time()
    logger.info(f"RAG query='{query}' entity={entity_type}")

    # Step 1: Retrieve relevant context via hybrid search
    search_result, context_parts, citations, t_retrieve_elapsed = _retrieve_context(query, entity_type, t_start)

    # Early return if ES is unreachable or no results
    early = _check_early_return(search_result, t_start)
    if early:
        return early

    context_text = "\n".join(context_parts)

    # Step 3: Build messages and call LLM
    answer, t_llm_elapsed = _call_llm(context_text, query, t_start)

    t_elapsed = time.time() - t_start
    return {
        "answer": answer,
        "citations": citations,
        "results": search_result["results"],
        "timing": {
            "total_seconds": round(t_elapsed, 3),
            "retrieve_seconds": round(t_retrieve_elapsed, 3),
            "llm_seconds": round(t_llm_elapsed, 3),
        },
        "query": query,
        "entity_type": entity_type or "",
    }


def rag_answer_multimodal(
    query: str,
    images: list[dict],
    entity_type: Optional[str] = None,
) -> dict:
    """Generate a RAG answer with image support (multimodal).

    Retrieves text context via hybrid search, then sends both text context
    AND images to a vision-capable LLM for a grounded answer.

    Args:
        query: The user's natural language question.
        images: List of prepared image dicts from :func:`prepare_image`.
                Each must have keys ``base64_data`` and ``mime_type``.
        entity_type: Optional entity filter to narrow the search.

    Returns:
        dict with keys:
            answer:      The LLM-generated answer text.
            citations:   List of source documents used.
            results:     Full search results for display.
            timing:      Timing breakdown for observability.
    """
    t_start = time.time()
    logger.info(f"RAG multimodal query='{query}' entity={entity_type} images={len(images)}")

    # Step 1: Retrieve relevant context via hybrid search
    search_result, context_parts, citations, t_retrieve_elapsed = _retrieve_context(query, entity_type, t_start)

    # Early return if ES is unreachable
    es_error = search_result.get("es_error")
    if es_error:
        t_elapsed = time.time() - t_start
        return {
            "answer": "Elasticsearch is not reachable. Please ensure the Elasticsearch server is running and try again.",
            "citations": [],
            "results": [],
            "es_error": es_error,
            "timing": {"total_seconds": round(t_elapsed, 3)},
        }

    context_text = "\n".join(context_parts) if context_parts else ""

    # Step 2: Build the user message
    if context_text:
        user_message = f"## Context from PLM database\n{context_text}\n\n## Question\n{query}"
    else:
        user_message = f"## Question\n{query}" if query else "Describe the attached image(s)."

    # Step 3: Call vision LLM with context + images
    vision_model = VISION_MODEL or CHAT_MODEL
    t_llm_start = time.time()
    logger.info(f"RAG multimodal LLM: model={vision_model} context={len(context_text)} chars images={len(images)}")

    try:
        answer = vision_chat(
            system_prompt=_RAG_SYSTEM_PROMPT,
            user_message=user_message,
            images=images,
            model=vision_model,
            max_tokens=4096,
        )
    except Exception as e:
        logger.error(f"RAG multimodal LLM call failed: {e}")
        answer = f"Error generating answer: {e}"
    t_llm_elapsed = time.time() - t_llm_start
    logger.info(f"RAG multimodal LLM generated {len(answer)} chars in {t_llm_elapsed:.3f}s")

    t_elapsed = time.time() - t_start
    return {
        "answer": answer,
        "citations": citations,
        "results": search_result.get("results", []),
        "timing": {
            "total_seconds": round(t_elapsed, 3),
            "retrieve_seconds": round(t_retrieve_elapsed, 3),
            "llm_seconds": round(t_llm_elapsed, 3),
        },
        "query": query,
        "entity_type": entity_type or "",
        "multimodal": True,
    }


# ── Shared helpers ──────────────────────────────────────────────


def _retrieve_context(query: str, entity_type: Optional[str], t_start: float):
    """Run hybrid search and build context parts + citations.

    Returns:
        (search_result, context_parts, citations, retrieve_elapsed)
    """
    t_retrieve_start = time.time()
    search_result = hybrid_search(
        query=query,
        entity_type=entity_type,
        page=1,
        size=RAG_MAX_CONTEXT_DOCS,
        search_mode="rag",
    )
    t_retrieve_elapsed = time.time() - t_retrieve_start
    logger.info(f"RAG retrieved {len(search_result.get('results', []))} results in {t_retrieve_elapsed:.3f}s")

    context_parts = []
    citations = []
    for i, r in enumerate(search_result.get("results", []), 1):
        context_parts.append(
            f"[{i}] ({r['entity_label']}) {r['title']}\n"
            f"    Details: {r['snippet']}\n"
        )
        citations.append({
            "number": i,
            "title": r["title"],
            "entity_label": r["entity_label"],
            "snippet": r["snippet"],
        })

    return search_result, context_parts, citations, t_retrieve_elapsed


def _check_early_return(search_result: dict, t_start: float) -> dict | None:
    """Return a result dict if we should early-exit, or None to continue."""
    es_error = search_result.get("es_error")
    if es_error:
        logger.warning(f"RAG: ES unreachable: {es_error}")
        return {
            "answer": "Elasticsearch is not reachable. Please ensure the Elasticsearch server is running and try again.",
            "citations": [],
            "results": [],
            "es_error": es_error,
            "timing": {"total_seconds": round(time.time() - t_start, 3)},
        }

    embed_error = search_result.get("embed_error")
    if embed_error:
        logger.warning(f"RAG: embedding failed: {embed_error}")
        return {
            "answer": "The embedding service is not reachable, so semantic search is unavailable. Please try again later or use BM25 keyword search.",
            "citations": [],
            "results": [],
            "embed_error": embed_error,
            "timing": {"total_seconds": round(time.time() - t_start, 3)},
        }

    if not search_result.get("results"):
        return {
            "answer": "I don't have enough information to answer this. No relevant documents were found.",
            "citations": [],
            "results": [],
            "timing": {"total_seconds": round(time.time() - t_start, 3)},
        }

    return None


def _call_llm(context_text: str, query: str, t_start: float) -> tuple[str, float]:
    """Build messages and call text LLM. Returns (answer_text, llm_elapsed)."""
    t_llm_start = time.time()
    messages = [
        {"role": "system", "content": _RAG_SYSTEM_PROMPT},
        {"role": "user", "content": f"## Context\n{context_text}\n\n## Question\n{query}"},
    ]

    logger.debug(f"RAG LLM prompt: {len(context_text)} chars context, {len(query)} chars query")
    try:
        answer = chat(messages, model=CHAT_MODEL)
    except Exception as e:
        logger.error(f"RAG LLM call failed: {e}")
        answer = f"Error generating answer: {e}"
    t_llm_elapsed = time.time() - t_llm_start
    logger.info(f"RAG LLM generated {len(answer)} chars in {t_llm_elapsed:.3f}s")
    return answer, t_llm_elapsed

"""aisearch — RAG-based semantic search for PLM-IQ.

This package implements hybrid search (BM25 + vector + RRF) across
structured PLM data (parts, BOM, costing, ECO, AML, AVL, CAD) and
unstructured PDF documents using Elasticsearch with LLM-powered RAG.

Module structure (separation of concerns):
    search.py       — Main entry point; orchestrates search and formats results.
    bm25.py         — Pure BM25 keyword search functions.
    bm25vectorrrf.py — Hybrid search (BM25 + vector kNN) with RRF fusion.
    ragai.py        — RAG answer generation with LLM and citations.
    router.py       — FastAPI routes for search UI and JSON API.
    config.py       — Configuration loaded from environment variables.
    es_client.py    — Elasticsearch client connection.
    llm_client.py   — LLM API client for embeddings and chat.
    vision.py       — Multimodal search with image support.

Public API:
    search()        — Main search function (mode: bm25, rag, hybrid).
    rag_answer()    — Generate RAG answer with citations.
    ENTITY_LABELS   — Dict mapping index names to display labels.
"""

from .search import search, ENTITY_LABELS
from .ragai import rag_answer, rag_answer_multimodal

__all__ = ["search", "rag_answer", "rag_answer_multimodal", "ENTITY_LABELS"]

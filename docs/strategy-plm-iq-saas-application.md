# PLM-IQ SaaS Application Strategy Document
# ... [existing content up to line 1325] ...

## 27. Metadata-Only RAG Implementation Plan

### Overview
This section describes the implementation of a Retrieval-Augmented Generation (RAG) system that operates exclusively on the existing graph metadata (vertices and edges) without requiring document content extraction or new Elasticsearch indices. The RAG system enhances the platform's AI capabilities by providing grounded, citation-backed answers to natural language queries while preserving the existing BM25 search functionality and adding semantic search via precomputed vertex embeddings.

### Components and Responsibilities
| Component | Responsibility |
|-----------|----------------|
| **Retrieval** | `SearchService.hybrid(tenant, query, rerank=True)` – Combines BM25 (multi_match on name/description/etc.) and semantic search (knn on vertex `semantic_embedding` field) using native Elasticsearch RRF fusion (`rank:{rrf:{}}`), with optional cross-encoder reranking. Returns top-K vertices/edges with scores, highlights, titles, URLs, and entity metadata. Context chunks = entity rows. |
| **Generation** | `RAGService` – Constructs a prompt using system instructions (tenant-scoped, anti-hallucination, citation requirements) + retrieved context (formatted as `[entity_type:id] title — subtitle/highlight`) + user query. Calls an LLM (OpenAI via swappable client interface) to generate an answer with inline citations `[vertex:uuid]` / `[edge:uuid]`. Returns the answer and a list of cited object IDs for verification. |
| **Storage** | No changes to indices or schemas required. Relies on: <ul><li>Existing `semantic_embedding` field (dense_vector) in vertex/edge indices, populated by the `EmbeddingsGenerator` service.</li><li>Existing BM25 search fields (name, description, number, kind, etc.).</li></ul> |
| **Guardrails** | Enforces tenant-scoped retrieval only; query sanitization; per-tenant model allowlists; token budgets; circuit breakers that degrade to non-AI flows on budget exhaustion; audit logging of queries, context IDs, model used, token consumption, and latency. |

### Data Flow (Per Query)
1. User submits a natural-language query via the RAG endpoint.
2. `RAGService` delegates retrieval to `SearchService.hybrid(tenant, query, rerank=True)` to obtain top-K context rows (vertices/edges).
3. Each context row is formatted into a prompt snippet: `[entity_type:id] title — subtitle/highlight`.
4. The full prompt is assembled: system instructions + context snippets + user query.
5. The prompt is sent to the LLM (OpenAI chat/completion endpoint).
6. The LLM returns an answer with inline citations referencing the context rows.
7. The `RAGService` extracts cited object IDs and returns the final answer with citations and context count.

### Phasing
1. **Verify Retrieval Readiness**: Confirm that vertex semantic embeddings are populated via the `EmbeddingsGenerator` service (jobs completed) and that `SearchService.hybrid()` with reranking returns relevant metadata rows.
2. **Implement `RAGService`**: Create the service with:
   - `retrieve(tenant, query, limit=10)` → delegates to `SearchService.hybrid(..., rerank=True)`.
   - `generate(query, context_rows)` → builds prompt, calls LLM, returns answer + citations.
   - Prompt templates per use case (conversational search, change assistant, document intelligence, etc.) aligned with Section 14 capabilities.
3. **Wire Endpoints**: Add API endpoints such as:
   - `POST /rag/ask` → `{tenant, query}` → returns `{answer, citations:[{entity_type, id, title, url}], context_count}`.
   - `POST /rag/conversational` → includes conversation history in context.
   - `POST /rag/change-assistant` → `{tenant, change_id, question}` → scoped retrieval + generation.
4. **Apply Guardrails**: Implement per-tenant AI budgets, model allowlists, prompt sanitization, and audit logging per Section 14 of the strategy document.
5. **Validation**: Compile-check the new service; write stubbed unit tests mocking `SearchService` and the LLM client to verify prompt assembly and response formatting without live API calls.

### Non-Goals (Out of Scope for v1)
- No document content extraction, chunking, or new Elasticsearch indices (pure metadata RAG).
- No fine-tuning or custom model training — uses approved endpoints via API.
- No complex reasoning chains (ReAct, etc.) — simple retrieve-then-generate.
- No UI integration beyond API endpoints (to be integrated into existing chat/search UI later).
- No multimodal support (text-only for v1).

### Integration with Existing Strategy
This metadata-only RAG system directly satisfies the AI capabilities listed in Section 15 of the strategy document:
- **Conversational search** (§15.15.7): Users ask natural-language questions about the product graph.
- **Change assistant** (§15.15.12): Summarizes changes and identifies affected objects using retrieved context.
- **Document intelligence** (§15.15.9): While full document intelligence requires content extraction, metadata-only RAG can still extract classifications, specifications, and requirements from vertex/edge metadata (e.g., from `solutionAttributes` and `tenantAttributes`).
- **Relationship suggestions** (§15.15.11): Suggests probable links between objects based on retrieved context.
- **Data quality validation** (§15.15.10): Identifies incomplete or inconsistent records via queried metadata.
- **Specification comparison** (§15.15.14): Compares specifications across revisions or versions using retrieved metadata.
- **Regulatory traceability** (§15.15.15): Helps identify products affected by regulatory changes via retrieved metadata.

The system adheres to the AI guardrails in Section 14:
- Retrieval is tenant-scoped and permission-aware (enforced by `SearchService`).
- AI-generated content is clearly identified as such.
- High-impact actions (e.g., releasing parts, approving changes) require user approval.
- AI recommendations include traceable source objects via citations.
- Sensitive-data handling aligns with contractual and regulatory requirements via tenant isolation and approved model endpoints.

### Benefits
- **Zero storage changes**: Leverages existing Elasticsearch indices and vector embeddings.
- **Immediate value**: Enhances search and AI capabilities without modifying the core graph storage or search infrastructure.
- **Strong grounding**: Answers are backed by verifiable metadata from the product graph.
- **Scalable**: Builds on existing asynchronous indexing and job processing patterns (`JobRegistry`).
- **Compliant**: Maintains tenant isolation, data residency, and auditability as required by Sections 4, 16, and 17.
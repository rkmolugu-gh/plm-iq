# aisearch — RAG Search System Overview

The `aisearch/` package implements a **hybrid search (BM25 + vector) + RAG** system on top of Elasticsearch for the PLM-IQ. It searches across both structured data (Parts, BOM, Costing, ECO, AML, AVL, CAD) and unstructured documents (PDF spec sheets) from a single search interface.

---

## Architecture Flow

```
User Query
    │
    ▼
┌─────────────────────────┐
│   /search  (SSR page)   │   ← FastAPI router (router.py)
│   /search/api (JSON)    │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│   BM25 mode?  RAG mode? │   ← search_mode selection
└──────┬──────────┬───────┘
       │          │
       ▼          ▼
┌──────────┐  ┌──────────────────────┐
│ hybrid_  │  │   rag_answer()       │
│ search() │  │  ┌───────────────┐   │
│ (BM25)   │  │  │ hybrid_search │   │
│          │  │  │ (RAG mode)    │   │
│          │  │  └───────┬───────┘   │
│          │  │          ▼           │
│          │  │  ┌───────────────┐   │
│          │  │  │ Build context  │   │
│          │  │  │ → LLM call     │   │
│          │  │  │ → answer+cites │   │
│          │  │  └───────────────┘   │
└──────────┘  └──────────────────────┘
       │          │
       ▼          ▼
┌────────────────────────────────────┐
│  Python RRF Engine                 │
│  ┌────────────┐ ┌───────────────┐  │
│  │ ES BM25 q. │ │ ES kNN query  │  │
│  │ (separate) │ │  (separate)   │  │
│  └─────┬──────┘ └──────┬────────┘  │
│        └─── RRF ───────┘           │
│        Python _rrf_fusion()        │
│        score = 1/(60 + rank)       │
└────────────────────────────────────┘
```

---

## File-by-File Explanation

### 1. Core Configuration

**`config.py`** — Central configuration module. Reads all settings from environment variables with sensible defaults:

| Setting | Default | Purpose |
|---|---|---|
| `ES_HOST` | `http://localhost:9200` | Elasticsearch address |
| `LLM_API_KEY` | `""` | LLM API key for the OpenAI-compatible endpoint (must be set in .env or env var) |
| `LLM_BASE_URL` | `""` | OpenAI-compatible API base URL (set in .env) |
| `EMBEDDING_MODEL` | `bge-m3` | 1024-dim embedding model |
| `CHAT_MODEL` | `deepseek-v4-flash` | Chat model for RAG answer generation |
| `EMBEDDING_DIMENSIONS` | `1024` | Vector dimension count |
| `ALL_INDICES` | (8 index names) | `plm_parts`, `plm_bom`, `plm_costing`, `plm_eco`, `plm_aml`, `plm_avl`, `plm_cad`, `plm_docs` |
| `SEARCH_DEFAULT_SIZE` | `10` | Results per page |
| `RAG_MAX_CONTEXT_DOCS` | `10` | Documents fed to LLM for context |
| `validate()` | — | Returns warnings for missing config (API key, etc.) |

**Important**: The API key is **never hardcoded** in code. It must be set as `LLM_API_KEY` environment variable or in the project-root `.env`.

---

### 2. External Service Clients

**`llm_client.py`** — Python client for the LLM API (OpenAI-compatible):

```python
embed(text, model="bge-m3") → list[float]   # Returns 1024-dim vector
chat(messages, model="deepseek-v4-flash") → str  # Returns generated text
```

- Used directly for query embedding if the ES inference pipeline falls back
- Used for RAG answer generation (chat)
- 30s timeout for embedding, 60s for chat
- Has detailed logging at `DEBUG` level showing request/response timing

**`es_client.py`** — Elasticsearch client with index management:

```python
get_es() → Elasticsearch           # Singleton ES connection
close_es()                          # Cleanup
create_index(name, force_delete)    # Create index with proper mappings
setup_inference_pipeline()          # Create inference endpoint + ingest pipeline
```

- Connects to ES at `ES_HOST` (default `http://localhost:9200`)
- Each index gets: `content` (text), `content_vector` (dense_vector, 1024-dim, cosine similarity), `entity_type` (keyword), plus entity-specific fields
- Embeddings are generated in Python via `llm_client` during staging and stored in `content_vector`

---

### 3. One-Time Setup

**`setup_es.py`** — Run once to prepare ES:

```
python -m aisearch.setup_es [--force]
```

This provisions all **8 indices** with proper mappings (text, keyword, dense_vector fields).
Embeddings are generated in Python (llm_client) during staging, not by ES.

The `--force` flag deletes and recreates the indices before provisioning.

---

### 4. Index Builders

Located in `db/indexing/`. These scripts read data from SQLite (via SQLAlchemy) or from PDFs, stage JSON documents to a backend-neutral store, and generate embeddings in Python. A separate publish step pushes them to ES.

| File | Source | What It Indexes | Content Field Built From |
|---|---|---|---|
| `base.py` | — | Abstract `BaseIndexBuilder` class | Shared logic: connect DB, push to ES, log progress |
| `build_parts.py` | `parts` table | Part number, name, revision, material, status | `"{part_number} {part_name} {material} {spec_file} {status}"` |
| `build_bom.py` | `bom` table | BOM entries with hierarchy | `"{part_number} {part_name} {parent_assembly} {bom_type}"` |
| `build_costing.py` | `costing_bom` table | Cost breakdown by part | `"{part_number} {part_name} ... costs ... {cost_type}"` |
| `build_eco.py` | `engineering_change_orders` table | ECOs with descriptions | `"{eco_number} {title} {description} {change_detail} {part_number}"` |
| `build_aml.py` | `approved_manufacturer_list` table | Manufacturer info | `"{part_number} {manufacturer_name} {mpn} Quality: {rating}"` |
| `build_avl.py` | `approved_vendor_list` table | Vendor/supplier info | `"{part_number} {vendor_name} {vpn}"` |
| `build_cad.py` | `cad_metadata` table | CAD file metadata | `"{file_name} {system} {drawing_number} {format} {part_number}"` |
| `build_docs.py` | `data/volume/*.pdf` | PDF text content per page | Extracted text via pypdf, chunked by page |
| `build_all.py` | — | Orchestrator | Runs all 8 builders sequentially with progress summary |

Key design: Each builder creates a `content` field that concatenates all relevant text fields. Python generates the vector embedding from this `content` field during staging. This ensures the vector captures meaning across all fields.

---

### 5. Search Engine

**`search.py`** — Core hybrid search function:

```python
hybrid_search(query, entity_type, page, size, search_mode) → dict
```

The `search_mode` parameter controls behavior:

**BM25 mode** (keyword search):
- Runs a `multi_match` query on `content^2` + all other fields
- Best for: known part numbers, exact terms, narrow queries
- Fast (no embedding needed)

**RAG mode** (hybrid search):
1. Embeds the query via Python `llm_client` (calls the LLM API directly)
2. Runs BM25 match on the `content` field as a **separate ES query**
3. Runs kNN search against `content_vector` as a **separate ES query** (20 nearest neighbors, 50 candidates)
4. Fuses results in Python via **RRF (Reciprocal Rank Fusion)** — `_rrf_fusion()` implements `score = 1/(60+rank)`
- Best for: natural language queries, conceptual matching
- Avoids ES built-in RRF (requires a Platinum license the free tier doesn't have)

Entity type filtering:
- `entity_type="Parts"` → searches only `plm_parts` index
- `entity_type=""` → searches all 8 indices
- Resolution is case-insensitive and supports partial matching

Return value includes full `timing` breakdown: `total_seconds`, `embed_seconds`, `search_seconds`.

---

### 6. RAG Engine

**`rag.py`** — Retrieval Augmented Generation:

```python
rag_answer(query, entity_type) → dict
```

Flow:
1. **Retrieve**: Calls `hybrid_search()` in RAG mode to get top 10 results
2. **Build context**: Formats results as structured text with `[N]` citation markers
3. **Generate**: Calls `deepseek-v4-flash` via `llm_client.chat()` with:
   - System prompt: "Answer ONLY using context below. Cite with [N]."
   - User message: context + question
4. **Return**: Answer text + citations list + search results + timing breakdown

Example:
```
Query: "what is the cost of brake assembly?"
→ Retrieves costing data for BRK-001, BRK-002, BRK-003
→ LLM generates: "The brake assembly (BRK-001) costs $18.75... [1][2]"
→ Response includes citations [1] and [2] linking to source docs
```

---

### 7. FastAPI Router (UI + API)

**`router.py`** — Two endpoints:

| Endpoint | Method | Purpose | Parameters |
|---|---|---|---|
| `/search` | GET | Server-rendered search page | `?q=&mode=bm25/rag&entity=&page=` |
| `/search/api` | GET | JSON API for async clients | Same as above |

The SSR endpoint renders `search.html` and returns full HTML. The JSON endpoint returns structured data (`application/json`).

Template `templates/search.html`:
- Extends `app/templates/base.html` (Bootstrap 5.3 dark theme)
- Search bar with mode dropdown (BM25 / RAG)
- Entity type filter dropdown
- RAG answer box with AI answer + numbered citations
- Results list with entity badges, scores, snippets
- Pagination
- Collapsible "Search Telemetry" panel showing timing breakdown

---

### 8. Batch Files

| File | Prerequisites Checked | Action |
|---|---|---|
| `start_es.bat` | ES installation path exists, ES not already running | Launches `elasticsearch.bat` in a new window |
| `build_indices.bat` | Python installed, ES running, LLM_API_KEY set, optional: pypdf/elasticsearch packages | Runs `setup_es.py`, then `build_all.py`. Supports `--force` flag. |
| `rebuild_indices.bat` | Same as build | Asks confirmation, then runs build with `--force` |

---

## Key Design Decisions

1. **Embeddings generated in Python**: During staging, the LLM API embeds the `content` field and the vector is stored in `content_vector`. This avoids ES inference pipeline licensing and keeps the search backend swappable.

2. **Two search modes, not one**: BM25 mode skips vector operations entirely — faster for exact match queries. RAG mode uses full hybrid search with RRF — better for natural language. Users can choose based on their query type.

3. **Manual RRF in Python**: The ES built-in RRF (`"rank": {"rrf": {}}`) requires a Platinum/Enterprise license. Instead, BM25 and kNN are run as **two separate ES queries** and fused in Python via `_rrf_fusion()`. The formula `score = 1/(60+rank)` is identical to ES's RRF, producing the same hybrid relevance without any license cost.

4. **Single content field for embedding**: All entity-specific text is concatenated into a single `content` field that ES uses for vector generation. This ensures the vector captures the full meaning of each document, not just one field.

5. **Telemetry exposed in UI**: The "Search Telemetry" panel shows timing breakdown for every query. This helps with debugging, performance tuning, and understanding which search mode works best for different query types.

6. **Query embedding in Python**: The query is embedded via `llm_client.embed()` against the LLM API; there is no ES inference pipeline dependency.

---

## Running Order

```
1. set LLM_API_KEY=your-key-here         # Set API key
2. aisearch\start_es.bat                  # Start Elasticsearch
3. aisearch\build_indices.bat             # Setup ES + build all indices
4. python -m app.main                     # Start the web app
5. http://localhost:8000/search           # Use the search page
```

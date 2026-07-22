"""Indexing pipeline — stage source data, then publish to a search backend.

Two decoupled phases:
  1. Stage   (build_*.py + staging.py): each builder reads source data
     (SQLAlchemy model or PDF file), embeds the content via the LLM API,
     and writes backend-neutral JSONL documents to the staging store.
  2. Publish (publish.py + aisearch/backend.py): staged documents are pushed to
     the configured SearchBackend (Elasticsearch today) in bulk batches.

Because builders never touch the search engine, the backend can be swapped
without changing any builder code. Run the whole pipeline with build_all.py.
"""

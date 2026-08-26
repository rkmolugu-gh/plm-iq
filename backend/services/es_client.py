"""EsClient - minimal REST transport for basic-license Elasticsearch.

Why this class exists
---------------------
Two services (search and ingest) used to carry private copies of the same
urllib plumbing. One client means one place for auth headers, timeouts, URL
resolution, and error translation - and a single seam to mock in tests or
replace with the official client later.

Benefits
--------
* Standard-library only: no client/server version coupling, no paid features.
* Auth config (API key / basic) is read once per instance, not per call.

How to extend (future scenarios)
--------------------------------
* New endpoint needs -> add a thin method here (e.g. ``bulk``) instead of
  calling ``request`` from services.
* Official elasticsearch-py client -> subclass and override ``request``;
  SearchService/IngestService keep working untouched.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from .errors import ServiceError

logger = logging.getLogger(__name__)


class EsClient:
    def __init__(self, url: str | None = None, timeout: float | None = None):
        self.url = (url or os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")).rstrip("/")
        self.timeout = timeout if timeout is not None else float(os.getenv("ELASTICSEARCH_TIMEOUT", "30"))

    def request(self, method: str, path: str, *, body: bytes | None = None,
                content_type: str = "application/json") -> tuple[int, dict | list]:
        request = urllib.request.Request(f"{self.url}{path}", data=body, method=method)
        request.add_header("Accept", "application/json")
        api_key = os.getenv("ELASTICSEARCH_API_KEY")
        username = os.getenv("ELASTICSEARCH_USERNAME") or os.getenv("ES_USER") or "elastic"
        password = os.getenv("ELASTICSEARCH_PASSWORD", "") or os.getenv("ES_PASSWORD", "")
        if api_key:
            request.add_header("Authorization", f"ApiKey {api_key}")
        elif username:
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            request.add_header("Authorization", f"Basic {token}")
        if body is not None:
            request.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
                return response.status, json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            return exc.code, {"error": detail}
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ServiceError(f"elasticsearch unreachable at {self.url}: {exc}") from exc

    def root_info(self) -> dict:
        status, payload = self.request("GET", "/")
        if status != 200:
            raise ServiceError(f"elasticsearch responded with HTTP {status}: {payload.get('error', '')}")
        return payload  # type: ignore[return-value]

    def ping(self) -> bool:
        try:
            self.root_info()
        except ServiceError:
            return False
        return True

    def cluster_status(self) -> dict:
        """Connection summary for the admin page; never raises when offline."""
        try:
            info = self.root_info()
        except ServiceError as exc:
            return {"online": False, "url": self.url, "version": None, "error": str(exc)}
        return {
            "online": True,
            "url": self.url,
            "version": info.get("version", {}).get("number"),
            "error": None,
        }

    @staticmethod
    def quote_path(value: str) -> str:
        """URL-quote an index name for path embedding."""
        return urllib.parse.quote(value)


#: Shared transport singleton for search + ingest.
es = EsClient()

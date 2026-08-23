"""Host-header resolution for the PLM-IQ gateway.

Dev domain contract (strategy Section 6): ``{tenant}.{edition}.localhost.com``
or ``{tenant}.{edition}.localhost``. Tenant slugs are lowercase letters,
digits, hyphens; editions are controlled platform values. Anything else is an
invalid context and renders the branded "page not found" page.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

EDITIONS = ("foundation", "discrete", "process", "food")

EDITION_LABELS = {
    "foundation": "Foundation",
    "discrete": "Discrete",
    "process": "Process",
    "food": "Food",
}

_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")

# Dev suffixes always accepted; production adds the deployed base domain
# (BASE_DOMAIN, comma-separated for co-hosted domains).
_PROD_SUFFIXES = tuple(
    s.strip().lower().lstrip(".") for s in os.getenv("BASE_DOMAIN", "").split(",") if s.strip()
)
_SUFFIXES = ("localhost.com", "localhost") + _PROD_SUFFIXES


@dataclass(frozen=True)
class TenantContext:
    tenant: str = ""
    edition: str = ""
    edition_label: str = ""
    host: str = ""
    valid: bool = False
    matched_pattern: bool = False


_INVALID = TenantContext()


def resolve_host(host_header: str | None) -> TenantContext:
    """Classify a Host header into one of three outcomes.

    valid            - {tenant}.{edition}.<suffix> with legal values: serve the workspace.
    matched_pattern  - host is inside the workspace namespace but malformed: branded 404.
    neither          - bare IPs, localhost, foreign domains: serve the default info page.
    """
    if not host_header:
        return _INVALID
    host = host_header.strip().split(":")[0].lower().rstrip(".")
    for suffix in _SUFFIXES:
        if not host.endswith("." + suffix):
            continue
        labels = host[: -(len(suffix) + 1)].split(".")
        if len(labels) == 2 and _TENANT_RE.match(labels[0]) and labels[1] in EDITIONS:
            ctx = TenantContext(
                tenant=labels[0],
                edition=labels[1],
                edition_label=EDITION_LABELS[labels[1]],
                host=host,
                valid=True,
                matched_pattern=True,
            )
            logger.info("gateway.host.resolved", extra={"host": host, "tenant": ctx.tenant, "edition": ctx.edition})
            return ctx
        logger.warning("gateway.host.rejected", extra={"host": host})
        return TenantContext(host=host, matched_pattern=True)
    logger.warning("gateway.host.unrecognized", extra={"host": host})
    return TenantContext(host=host)

"""Host-header resolution for the PLM-IQ gateway.

Dev domain contract (strategy Section 6): ``{tenant}.{edition}.localhost.com``
or ``{tenant}.{edition}.localhost``. Tenant slugs are lowercase letters,
digits, hyphens; editions are controlled platform values. Anything else is an
invalid context and renders the branded "page not found" page.
"""
from __future__ import annotations

import logging
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

# dev suffixes a tenant workspace may live under
_SUFFIXES = ("localhost.com", "localhost")


@dataclass(frozen=True)
class TenantContext:
    tenant: str
    edition: str
    edition_label: str
    host: str
    valid: bool


_INVALID = TenantContext(tenant="", edition="", edition_label="", host="", valid=False)


def resolve_host(host_header: str | None) -> TenantContext:
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
            )
            logger.info("gateway.host.resolved", extra={"host": host, "tenant": ctx.tenant, "edition": ctx.edition})
            return ctx
        logger.warning("gateway.host.rejected", extra={"host": host})
        return TenantContext(tenant="", edition="", edition_label="", host=host, valid=False)
    logger.warning("gateway.host.unknown_suffix", extra={"host": host})
    return TenantContext(tenant="", edition="", edition_label="", host=host, valid=False)

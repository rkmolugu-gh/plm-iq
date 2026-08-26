"""TenantResolver - Host-header classification for the PLM-IQ gateway.

Dev domain contract (strategy Section 6): ``{tenant}.{edition}.localhost.com``
or ``{tenant}.{edition}.localhost``; production adds the deployed BASE_DOMAIN.
Tenant slugs are lowercase letters, digits, hyphens; editions are
configuration (Settings). Anything else is an invalid context and renders the
branded "page not found" page.

Why a class
-----------
The accepted suffix set and edition catalog are configuration, not code -
holding them on an instance means tests can construct a resolver for any
domain setup, and a future Settings reload rebuilds one object instead of
patching module globals.

How to extend (future scenarios)
--------------------------------
* Vanity domains (strategy Section 6 CNAME) -> add a lookup hook that maps
  custom hosts to (tenant, edition) before the pattern match.
* Path-based routing fallback -> another resolve_* method here.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from . import settings

logger = logging.getLogger(__name__)

_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")


@dataclass(frozen=True)
class TenantContext:
    tenant: str = ""
    edition: str = ""
    edition_label: str = ""
    host: str = ""
    valid: bool = False
    matched_pattern: bool = False


class TenantResolver:
    def __init__(self, *, editions: tuple[str, ...], base_domain: str = ""):
        self.editions = editions
        self.labels = dict(settings.EDITION_LABELS) or {
            code: settings.label_for(code) for code in editions
        }
        # Dev suffixes are always accepted; production adds the deployed base domain(s).
        prod_suffixes = tuple(
            s.strip().lower().lstrip(".") for s in base_domain.split(",") if s.strip()
        )
        self.suffixes: tuple[str, ...] = ("localhost.com", "localhost") + prod_suffixes

    def resolve(self, host_header: str | None) -> TenantContext:
        """Classify a Host header into one of three outcomes.

        valid            - {tenant}.{edition}.<suffix>: serve the workspace.
        matched_pattern  - inside the workspace namespace but malformed: branded 404.
        neither          - bare IPs, localhost, foreign domains: default info page.
        """
        invalid = TenantContext()
        if not host_header:
            return invalid
        host = host_header.strip().split(":")[0].lower().rstrip(".")
        for suffix in self.suffixes:
            if not host.endswith("." + suffix):
                continue
            labels = host[: -(len(suffix) + 1)].split(".")
            if len(labels) == 2 and _TENANT_RE.match(labels[0]) and labels[1] in self.editions:
                ctx = TenantContext(
                    tenant=labels[0],
                    edition=labels[1],
                    edition_label=self.labels.get(labels[1], labels[1]),
                    host=host,
                    valid=True,
                    matched_pattern=True,
                )
                logger.info("gateway.host.resolved", extra={
                    "host": host, "tenant": ctx.tenant, "edition": ctx.edition,
                })
                return ctx
            logger.warning("gateway.host.rejected", extra={"host": host})
            return TenantContext(host=host, matched_pattern=True)
        logger.warning("gateway.host.unrecognized", extra={"host": host})
        return TenantContext(host=host)


#: Shared singleton configured from the loaded Settings.
tenant_resolver = TenantResolver(editions=settings.EDITIONS, base_domain=settings.BASE_DOMAIN)

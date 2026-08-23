"""PLM-IQ API layer. Routers are added in a later milestone.

Routers may import from ``services`` only — never from ``services.tables``
directly — keeping the api -> services -> db dependency direction intact.
"""

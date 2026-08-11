"""Per-tenant Gitea separation for git-served files.

Provides a centralized Gitea client that isolates each tenant's CAD files and
document attachments into their own private repositories owned by their own
Gitea user. See docs/multitenant-gitea.md for the design.
"""

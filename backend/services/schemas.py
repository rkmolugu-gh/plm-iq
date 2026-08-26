"""Pydantic v2 DTOs shared by services and (later) the API layer.

camelCase aliases match the strategy-doc field names; construction accepts
snake_case too (populate_by_name). ``*Out`` models mirror full rows.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic.alias_generators import to_camel

from . import enums


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


def from_row(model_cls: type[CamelModel], row) -> Any:
    return model_cls.model_validate(dict(row._mapping))


# ── Vertex ──────────────────────────────────────────────────────────────────


class VertexCreate(CamelModel):
    edition_id: enums.EditionId
    kind: enums.VertexKind
    number: str
    name: str
    prefix: str = "V"
    revision: str = "A"
    description: str = ""
    classification_id: UUID | None = None
    release_on: date | None = None
    solution_attributes: dict[str, Any] = {}
    tenant_attributes: dict[str, Any] = {}


class VertexUpdate(CamelModel):
    version: int
    name: str | None = None
    description: str | None = None
    classification_id: UUID | None = None
    revision: str | None = None
    lifecycle_state: enums.LifecycleState | None = None
    release_on: date | None = None
    solution_attributes: dict[str, Any] | None = None
    tenant_attributes: dict[str, Any] | None = None


class VertexOut(CamelModel):
    id: UUID
    tenant_id: UUID
    edition_id: enums.EditionId
    kind: enums.VertexKind
    classification_id: UUID | None
    prefix: str
    number: str
    name: str
    description: str
    revision: str
    lifecycle_state: enums.LifecycleState
    release_on: date | None
    marked_for_deletion: bool
    version: int
    created_by: str
    created_on: datetime
    modified_by: str
    modified_on: datetime
    solution_attributes: dict[str, Any]
    tenant_attributes: dict[str, Any]


class DocumentCreate(VertexCreate):
    """Creation payload for kind=Document vertices (TSE composition).

    The kind is pinned: document_service routes the core write plus the
    foundation_document extension row, and both halves agree on the kind by
    construction. Accepting another kind here would silently create a vertex
    that belongs to a different subtype's feature set.
    """

    kind: enums.VertexKind = enums.VertexKind.DOCUMENT

    @model_validator(mode="after")
    def _kind_is_document(self) -> DocumentCreate:
        if self.kind != enums.VertexKind.DOCUMENT:
            raise ValueError("documentService creates kind='Document' vertices only")
        return self


class DocumentUpdate(VertexUpdate):
    """Core-field updates for a document.

    Subtype file metadata intentionally has no direct setters here: files
    change through the upload/download flow, which keeps storage keys and
    checksums consistent with the actual stored bytes.
    """


class DocumentOut(VertexOut):
    """Full document view: core vertex columns plus the extension columns.

    Mirrors one row of the ``v_document`` reporting view - this is the TSE
    promise: consumers see a single flat, fully typed object.
    """

    file_is_directory: bool = False
    file_name: str = ""
    file_parent_id: UUID | None = None
    file_full_path: str = ""
    file_size_bytes: int = 0
    file_mime_type: str = ""
    file_checksum_sha256: str = ""
    storage_key: str = ""


# ── Edge ────────────────────────────────────────────────────────────────────


class EdgeCreate(CamelModel):
    edition_id: enums.EditionId
    kind: enums.EdgeKind
    name: str
    source_vertex_id: UUID
    source_vertex_kind: enums.VertexKind
    target_vertex_id: UUID
    target_vertex_kind: enums.VertexKind
    prefix: str = "E"
    lifecycle_state: enums.EdgeState = enums.EdgeState.PENDING_APPROVAL
    effective_from: date | None = None
    effective_to: date | None = None
    graph_rule_id: UUID | None = None
    annotation: dict[str, Any] = {}
    tenant_attributes: dict[str, Any] = {}


class EdgeUpdate(CamelModel):
    version: int
    name: str | None = None
    lifecycle_state: enums.EdgeState | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    graph_rule_id: UUID | None = None
    annotation: dict[str, Any] | None = None
    tenant_attributes: dict[str, Any] | None = None


class EdgeOut(CamelModel):
    id: UUID
    tenant_id: UUID
    edition_id: enums.EditionId
    kind: enums.EdgeKind
    name: str
    source_vertex_id: UUID
    source_vertex_kind: enums.VertexKind
    target_vertex_id: UUID
    target_vertex_kind: enums.VertexKind
    lifecycle_state: enums.EdgeState
    effective_from: date | None
    effective_to: date | None
    graph_rule_id: UUID | None
    prefix: str
    version: int
    created_by: str
    created_on: datetime
    modified_by: str
    modified_on: datetime
    tenant_attributes: dict[str, Any]
    annotation: dict[str, Any]


# ── Graph rule ──────────────────────────────────────────────────────────────


class GraphRuleBase(CamelModel):
    scope: enums.RuleScope = enums.RuleScope.PLATFORM
    tenant_id: UUID | None = None
    edition_id: enums.EditionId | None = None
    edge_kind: enums.EdgeKind
    source_vertex_kind: enums.VertexKind
    target_vertex_kind: enums.VertexKind
    direction: enums.RuleDirection = enums.RuleDirection.SOURCE_TO_TARGET
    source_cardinality: enums.Cardinality = enums.Cardinality.ZERO_OR_MANY
    target_cardinality: enums.Cardinality = enums.Cardinality.ZERO_OR_MANY
    source_participation: enums.Participation = enums.Participation.OPTIONAL
    target_participation: enums.Participation = enums.Participation.OPTIONAL
    duplicate_edges_allowed: bool = False
    source_lifecycle_states: list[enums.LifecycleState] = []
    target_lifecycle_states: list[enums.LifecycleState] = []
    required_edge_attributes: list[str] = []
    allow_tenant_extension: bool = True

    @field_validator(
        "source_lifecycle_states", "target_lifecycle_states", "required_edge_attributes",
        mode="before",
    )
    @classmethod
    def _null_arrays_mean_empty(cls, value: Any) -> Any:
        """The DB columns are nullable; treat SQL NULL as an empty list."""
        return [] if value is None else value

    @model_validator(mode="after")
    def _scope_fields_match(self) -> GraphRuleBase:
        if (self.scope == enums.RuleScope.TENANT) != (self.tenant_id is not None):
            raise ValueError("scope 'tenant' requires tenantId; every other scope forbids it")
        if (self.scope == enums.RuleScope.EDITION) != (self.edition_id is not None):
            raise ValueError("scope 'edition' requires editionId; every other scope forbids it")
        return self


class GraphRuleCreate(GraphRuleBase):
    pass


class GraphRuleUpdate(CamelModel):
    version: int
    source_cardinality: enums.Cardinality | None = None
    target_cardinality: enums.Cardinality | None = None
    source_participation: enums.Participation | None = None
    target_participation: enums.Participation | None = None
    duplicate_edges_allowed: bool | None = None
    source_lifecycle_states: list[enums.LifecycleState] | None = None
    target_lifecycle_states: list[enums.LifecycleState] | None = None
    required_edge_attributes: list[str] | None = None
    allow_tenant_extension: bool | None = None


class GraphRuleOut(GraphRuleBase):
    id: UUID
    version: int
    created_by: str
    created_on: datetime
    modified_by: str
    modified_on: datetime


# ── Identity & access ───────────────────────────────────────────────────────


class TenantCreate(CamelModel):
    subdomain: str
    name: str
    contact_email: str
    secret: str
    edition_id: enums.EditionId = enums.EditionId.FOUNDATION


class TenantUpdate(CamelModel):
    version: int
    name: str | None = None
    contact_email: str | None = None
    edition_id: enums.EditionId | None = None
    status: enums.TenantStatus | None = None


class TenantOut(CamelModel):
    """Tenant row without ``secret``; rotation returns the new secret explicitly."""

    id: UUID
    subdomain: str
    name: str
    contact_email: str
    edition_id: enums.EditionId
    status: enums.TenantStatus
    version: int
    created_by: str
    created_on: datetime
    modified_by: str
    modified_on: datetime


class UserCreate(CamelModel):
    email: str
    full_name: str
    is_tenant_admin: bool = False
    password_hash: str | None = None
    mfa_enabled: bool = False
    role: str | None = None


class UserUpdate(CamelModel):
    version: int
    full_name: str | None = None
    is_tenant_admin: bool | None = None
    password_hash: str | None = None
    mfa_enabled: bool | None = None
    status: enums.UserStatus | None = None


class UserOut(CamelModel):
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    is_tenant_admin: bool
    status: enums.UserStatus
    mfa_enabled: bool
    last_login_on: datetime | None
    version: int
    created_by: str
    created_on: datetime
    modified_by: str
    modified_on: datetime


class RoleCreate(CamelModel):
    """Tenants author only scope='tenant' roles; scope/tenancy are service-assigned."""

    code: str
    name: str
    description: str = ""
    edition_scope: enums.EditionId | None = None


class RoleUpdate(CamelModel):
    version: int
    name: str | None = None
    description: str | None = None
    edition_scope: enums.EditionId | None = None


class RoleOut(CamelModel):
    id: UUID
    scope: enums.RoleScope
    tenant_id: UUID | None
    edition_scope: enums.EditionId | None
    code: str
    name: str
    description: str
    is_system: bool
    version: int
    created_by: str
    created_on: datetime
    modified_by: str
    modified_on: datetime


class PermissionOut(CamelModel):
    id: UUID
    code: str
    resource: str
    action: str
    description: str


class PermissionCreate(CamelModel):
    code: str
    resource: str
    action: str
    description: str = ""


class PermissionUpdate(CamelModel):
    code: str | None = None
    resource: str | None = None
    action: str | None = None
    description: str | None = None


# ── Settings ────────────────────────────────────────────────────────────────


class SettingOut(CamelModel):
    """One setting row. ``content`` is the full .env-style blob for its scope."""

    id: UUID
    level: enums.SettingLevel
    tenant_id: UUID | None = None
    user_id: UUID | None = None
    content: str
    is_secret: bool = False
    version: int
    created_by: str
    created_on: datetime
    modified_by: str
    modified_on: datetime


# ── Pagination ──────────────────────────────────────────────────────────────

ItemT = TypeVar("ItemT")


class Page(CamelModel, Generic[ItemT]):
    items: list[ItemT]
    total: int
    limit: int
    offset: int

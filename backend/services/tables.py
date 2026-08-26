"""SQLAlchemy Core mappings onto the existing plmiqdb graph-foundation tables.

The physical schema is owned by database/schema/*.sql (never create_all here;
these Table objects are DML-only). ``version`` is a database identity column
bumped by trigger, so services read it but never write it.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, MetaData, Table, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID

from . import enums

metadata = MetaData(schema="plmiqdb")


def _enum(py_enum, name: str) -> ENUM:
    return ENUM(py_enum, name=name, values_callable=lambda e: [m.value for m in e], create_type=False)


foundation_vertex = Table(
    "foundation_vertex",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("edition_id", _enum(enums.EditionId, "edition_id"), nullable=False),
    Column("kind", _enum(enums.VertexKind, "vertex_kind"), nullable=False),
    Column("classification_id", UUID(as_uuid=True)),
    Column("prefix", Text, nullable=False),
    Column("number", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("revision", Text, nullable=False),
    Column("lifecycle_state", _enum(enums.LifecycleState, "lifecycle_state"), nullable=False),
    Column("release_on", Date),
    Column("marked_for_deletion", Boolean, nullable=False),
    Column("version", BigInteger),
    Column("created_by", Text, nullable=False),
    Column("created_on", DateTime(timezone=True), nullable=False),
    Column("modified_by", Text, nullable=False),
    Column("modified_on", DateTime(timezone=True), nullable=False),
    Column("solution_attributes", JSONB, nullable=False),
    Column("tenant_attributes", JSONB, nullable=False),
)

# TSE extension table (strategy Section 8): carries ONLY document attributes
# and joins the core row by primary key. Every system attribute stays in
# foundation_vertex - this table must never grow copies of core columns, or
# the single-source-of-truth invariant behind the pattern erodes.
foundation_document = Table(
    "foundation_document",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("file_is_directory", Boolean, nullable=False),
    Column("file_name", Text, nullable=False),
    Column("file_parent_id", UUID(as_uuid=True)),
    Column("file_full_path", Text, nullable=False),
    Column("file_size_bytes", BigInteger, nullable=False),
    Column("file_mime_type", Text, nullable=False),
    Column("file_checksum_sha256", Text, nullable=False),
    Column("storage_key", Text, nullable=False),
)

foundation_graph_rule = Table(
    "foundation_graph_rule",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("scope", _enum(enums.RuleScope, "rule_scope"), nullable=False),
    Column("tenant_id", UUID(as_uuid=True)),
    Column("edition_id", _enum(enums.EditionId, "edition_id")),
    Column("edge_kind", _enum(enums.EdgeKind, "edge_kind"), nullable=False),
    Column("source_vertex_kind", _enum(enums.VertexKind, "vertex_kind"), nullable=False),
    Column("target_vertex_kind", _enum(enums.VertexKind, "vertex_kind"), nullable=False),
    Column("direction", _enum(enums.RuleDirection, "rule_direction"), nullable=False),
    Column("source_cardinality", _enum(enums.Cardinality, "cardinality"), nullable=False),
    Column("target_cardinality", _enum(enums.Cardinality, "cardinality"), nullable=False),
    Column("source_participation", _enum(enums.Participation, "participation"), nullable=False),
    Column("target_participation", _enum(enums.Participation, "participation"), nullable=False),
    Column("duplicate_edges_allowed", Boolean, nullable=False),
    Column("source_lifecycle_states", ARRAY(_enum(enums.LifecycleState, "lifecycle_state"))),
    Column("target_lifecycle_states", ARRAY(_enum(enums.LifecycleState, "lifecycle_state"))),
    Column("required_edge_attributes", ARRAY(Text())),
    Column("allow_tenant_extension", Boolean, nullable=False),
    Column("version", BigInteger),
    Column("created_by", Text, nullable=False),
    Column("created_on", DateTime(timezone=True), nullable=False),
    Column("modified_by", Text, nullable=False),
    Column("modified_on", DateTime(timezone=True), nullable=False),
)

foundation_edge = Table(
    "foundation_edge",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("edition_id", _enum(enums.EditionId, "edition_id"), nullable=False),
    Column("kind", _enum(enums.EdgeKind, "edge_kind"), nullable=False),
    Column("name", Text, nullable=False),
    Column("source_vertex_id", UUID(as_uuid=True), nullable=False),
    Column("source_vertex_kind", _enum(enums.VertexKind, "vertex_kind"), nullable=False),
    Column("target_vertex_id", UUID(as_uuid=True), nullable=False),
    Column("target_vertex_kind", _enum(enums.VertexKind, "vertex_kind"), nullable=False),
    Column("lifecycle_state", _enum(enums.EdgeState, "edge_state"), nullable=False),
    Column("effective_from", Date),
    Column("effective_to", Date),
    Column("graph_rule_id", UUID(as_uuid=True)),
    Column("prefix", Text, nullable=False),
    Column("version", BigInteger),
    Column("created_by", Text, nullable=False),
    Column("created_on", DateTime(timezone=True), nullable=False),
    Column("modified_by", Text, nullable=False),
    Column("modified_on", DateTime(timezone=True), nullable=False),
    Column("tenant_attributes", JSONB, nullable=False),
    Column("annotation", JSONB, nullable=False),
)

# ── Identity & access (database/schema/foundation_schema.sql) ───────────────

iam_tenant = Table(
    "iam_tenant",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("subdomain", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("contact_email", Text, nullable=False),
    Column("secret", Text, nullable=False),
    Column("edition_id", _enum(enums.EditionId, "edition_id"), nullable=False),
    Column("status", _enum(enums.TenantStatus, "iam_tenant_status"), nullable=False),
    Column("version", BigInteger),
    Column("created_by", Text, nullable=False),
    Column("created_on", DateTime(timezone=True), nullable=False),
    Column("modified_by", Text, nullable=False),
    Column("modified_on", DateTime(timezone=True), nullable=False),
)

iam_user = Table(
    "iam_user",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("email", Text, nullable=False),
    Column("full_name", Text, nullable=False),
    Column("is_tenant_admin", Boolean, nullable=False),
    Column("password_hash", Text),
    Column("status", _enum(enums.UserStatus, "iam_user_status"), nullable=False),
    Column("mfa_enabled", Boolean, nullable=False),
    Column("last_login_on", DateTime(timezone=True)),
    Column("version", BigInteger),
    Column("created_by", Text, nullable=False),
    Column("created_on", DateTime(timezone=True), nullable=False),
    Column("modified_by", Text, nullable=False),
    Column("modified_on", DateTime(timezone=True), nullable=False),
)

iam_role = Table(
    "iam_role",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("scope", _enum(enums.RoleScope, "iam_role_scope"), nullable=False),
    Column("tenant_id", UUID(as_uuid=True)),
    Column("edition_scope", _enum(enums.EditionId, "edition_id")),
    Column("code", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("is_system", Boolean, nullable=False),
    Column("version", BigInteger),
    Column("created_by", Text, nullable=False),
    Column("created_on", DateTime(timezone=True), nullable=False),
    Column("modified_by", Text, nullable=False),
    Column("modified_on", DateTime(timezone=True), nullable=False),
)

iam_permission = Table(
    "iam_permission",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("code", Text, nullable=False),
    Column("resource", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("description", Text, nullable=False),
)

iam_role_permission = Table(
    "iam_role_permission",
    metadata,
    Column("role_id", UUID(as_uuid=True), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
)

iam_user_role = Table(
    "iam_user_role",
    metadata,
    Column("user_id", UUID(as_uuid=True), primary_key=True),
    Column("role_id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("assigned_by", Text, nullable=False),
    Column("assigned_on", DateTime(timezone=True), nullable=False),
)

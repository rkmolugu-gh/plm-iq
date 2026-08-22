"""Generate PostgreSQL DDL and seed SQL from a resolved PLM-IQ profile.

The physical model follows the graph meta-model (metamodel-prd.md section 24):

    profile, tenant, app_user, role            platform
    vertex_type, attribute_definition          configurable vertex meta-model
    edge_type, edge_attribute_definition       configurable edge meta-model
    vertex, vertex_attribute                   nodes + typed attribute rows
    edge, edge_annotation                      edges + typed annotation rows
    vertex_revision                            immutable revision history
    lifecycle, lifecycle_state, ..._transition seeded lifecycle definitions
    graph_query                                seeded reusable queries
    workflow_definition/stage/instance/task    declarative workflows + runtime
    profile_section                            revision/search/ai/ui config
    audit_log                                  mutation audit trail

Seed rows use deterministic UUIDs (md5 of ``profile|kind|key``) so applying
a schema twice updates metadata in place instead of duplicating it.
"""

from __future__ import annotations

import json
from typing import Any

from engine.compiler.profile import ResolvedProfile, effective_properties

_VALUE_COLUMN: dict[str, str] = {
    "string": "value_string",
    "text": "value_string",
    "enum": "value_string",
    "reference": "value_string",
    "integer": "value_number",
    "decimal": "value_number",
    "boolean": "value_boolean",
    "date": "value_date",
    "datetime": "value_timestamp",
    "json": "value_json",
    "multi_reference": "value_json",
}

_INDEX_SUFFIX = {"value_string": "str", "value_number": "num", "value_date": "date"}

_DDL = """\
-- = PLATFORM =

CREATE TABLE IF NOT EXISTS profile (
    profile_id        text PRIMARY KEY,
    name              text NOT NULL,
    version           text NOT NULL,
    inherits          jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_files      jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenant (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug              text NOT NULL UNIQUE,
    name              text NOT NULL,
    primary_profile   text NOT NULL REFERENCES profile (profile_id),
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_user (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL REFERENCES tenant (id),
    email             text NOT NULL,
    password_hash     text NOT NULL,
    display_name      text,
    is_active         boolean NOT NULL DEFAULT TRUE,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_app_user_tenant_email UNIQUE (tenant_id, email)
);

CREATE TABLE IF NOT EXISTS role (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL REFERENCES tenant (id),
    code              text NOT NULL,
    name              text,
    CONSTRAINT uq_role_tenant_code UNIQUE (tenant_id, code)
);

-- = VERTEX META-MODEL =

CREATE TABLE IF NOT EXISTS vertex_type (
    id                uuid PRIMARY KEY,
    profile_id        text NOT NULL REFERENCES profile (profile_id),
    type_key          text NOT NULL,
    label             text NOT NULL,
    description       text,
    parent_key        text,
    is_abstract       boolean NOT NULL DEFAULT FALSE,
    is_system         boolean NOT NULL DEFAULT FALSE,
    display_order     integer NOT NULL DEFAULT 0,
    version           integer NOT NULL DEFAULT 1,
    effective_from    timestamptz NOT NULL DEFAULT now(),
    effective_to      timestamptz,
    CONSTRAINT uq_vertex_type_key UNIQUE (profile_id, type_key),
    CONSTRAINT fk_vertex_type_parent FOREIGN KEY (profile_id, parent_key)
        REFERENCES vertex_type (profile_id, type_key)
);

CREATE TABLE IF NOT EXISTS attribute_definition (
    id                uuid PRIMARY KEY,
    profile_id        text NOT NULL,
    vertex_type_key   text NOT NULL,
    name              text NOT NULL,
    label             text,
    description       text,
    data_type         text NOT NULL CHECK (
        data_type IN ('string', 'text', 'integer', 'decimal', 'boolean', 'date',
                      'datetime', 'enum', 'reference', 'multi_reference', 'json')),
    required          boolean NOT NULL DEFAULT FALSE,
    default_value     jsonb,
    enum_values       jsonb,
    unit              text,
    searchable        boolean NOT NULL DEFAULT FALSE,
    filterable        boolean NOT NULL DEFAULT FALSE,
    indexed           boolean NOT NULL DEFAULT FALSE,
    is_system         boolean NOT NULL DEFAULT FALSE,
    is_structural     boolean NOT NULL DEFAULT FALSE,
    display_order     integer NOT NULL DEFAULT 0,
    version           integer NOT NULL DEFAULT 1,
    effective_from    timestamptz NOT NULL DEFAULT now(),
    effective_to      timestamptz,
    CONSTRAINT uq_attribute_definition UNIQUE (profile_id, vertex_type_key, name),
    CONSTRAINT fk_attribute_definition_type FOREIGN KEY (profile_id, vertex_type_key)
        REFERENCES vertex_type (profile_id, type_key)
);

-- = EDGE META-MODEL =

CREATE TABLE IF NOT EXISTS edge_type (
    id                uuid PRIMARY KEY,
    profile_id        text NOT NULL REFERENCES profile (profile_id),
    edge_key          text NOT NULL,
    label             text NOT NULL,
    description       text,
    source_type_key   text NOT NULL,
    target_type_key   text NOT NULL,
    directed          boolean NOT NULL DEFAULT TRUE,
    is_symmetric      boolean NOT NULL DEFAULT FALSE,
    inverse_name      text,
    constraint_rules  jsonb NOT NULL DEFAULT '{}'::jsonb,
    version           integer NOT NULL DEFAULT 1,
    effective_from    timestamptz NOT NULL DEFAULT now(),
    effective_to      timestamptz,
    CONSTRAINT uq_edge_type_key UNIQUE (profile_id, edge_key),
    CONSTRAINT fk_edge_type_source FOREIGN KEY (profile_id, source_type_key)
        REFERENCES vertex_type (profile_id, type_key),
    CONSTRAINT fk_edge_type_target FOREIGN KEY (profile_id, target_type_key)
        REFERENCES vertex_type (profile_id, type_key)
);

CREATE TABLE IF NOT EXISTS edge_attribute_definition (
    id                uuid PRIMARY KEY,
    profile_id        text NOT NULL,
    edge_type_key     text NOT NULL,
    name              text NOT NULL,
    label             text,
    data_type         text NOT NULL CHECK (
        data_type IN ('string', 'text', 'integer', 'decimal', 'boolean', 'date',
                      'datetime', 'enum', 'reference', 'multi_reference', 'json')),
    required          boolean NOT NULL DEFAULT FALSE,
    default_value     jsonb,
    enum_values       jsonb,
    unit              text,
    searchable        boolean NOT NULL DEFAULT FALSE,
    filterable        boolean NOT NULL DEFAULT FALSE,
    indexed           boolean NOT NULL DEFAULT FALSE,
    display_order     integer NOT NULL DEFAULT 0,
    version           integer NOT NULL DEFAULT 1,
    effective_from    timestamptz NOT NULL DEFAULT now(),
    effective_to      timestamptz,
    CONSTRAINT uq_edge_attribute_definition UNIQUE (profile_id, edge_type_key, name),
    CONSTRAINT fk_edge_attribute_definition_type FOREIGN KEY (profile_id, edge_type_key)
        REFERENCES edge_type (profile_id, edge_key)
);

-- = GRAPH STORAGE =

CREATE TABLE IF NOT EXISTS vertex (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL REFERENCES tenant (id),
    vertex_type_id    uuid NOT NULL REFERENCES vertex_type (id),
    number            text NOT NULL,
    name              text NOT NULL,
    description       text,
    lifecycle_state   text NOT NULL DEFAULT 'DRAFT',
    revision          text,
    status            text NOT NULL DEFAULT 'ACTIVE',
    created_by        uuid REFERENCES app_user (id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    modified_by       uuid REFERENCES app_user (id),
    modified_at       timestamptz,
    CONSTRAINT uq_vertex_number UNIQUE (tenant_id, vertex_type_id, number)
);

CREATE TABLE IF NOT EXISTS vertex_attribute (
    vertex_id                uuid NOT NULL REFERENCES vertex (id) ON DELETE CASCADE,
    attribute_definition_id  uuid NOT NULL REFERENCES attribute_definition (id),
    ordinal                  integer NOT NULL DEFAULT 1,
    value_string             text,
    value_number             numeric,
    value_boolean            boolean,
    value_date               date,
    value_timestamp          timestamptz,
    value_json               jsonb,
    CONSTRAINT pk_vertex_attribute PRIMARY KEY (vertex_id, attribute_definition_id, ordinal),
    CONSTRAINT ck_vertex_attribute_value CHECK (
        value_string IS NOT NULL OR value_number IS NOT NULL OR value_boolean IS NOT NULL
        OR value_date IS NOT NULL OR value_timestamp IS NOT NULL OR value_json IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS edge (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL REFERENCES tenant (id),
    edge_type_id      uuid NOT NULL REFERENCES edge_type (id),
    source_vertex_id  uuid NOT NULL REFERENCES vertex (id),
    target_vertex_id  uuid NOT NULL REFERENCES vertex (id),
    status            text NOT NULL DEFAULT 'ACTIVE',
    effective_from    timestamptz,
    effective_to      timestamptz,
    source_ref_type   text,
    source_ref_id     text,
    confidence        numeric CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_by        uuid REFERENCES app_user (id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    modified_by       uuid REFERENCES app_user (id),
    modified_at       timestamptz,
    CONSTRAINT uq_edge_occurrence UNIQUE (tenant_id, edge_type_id, source_vertex_id, target_vertex_id)
);

CREATE TABLE IF NOT EXISTS edge_annotation (
    edge_id                       uuid NOT NULL REFERENCES edge (id) ON DELETE CASCADE,
    edge_attribute_definition_id  uuid NOT NULL REFERENCES edge_attribute_definition (id),
    ordinal                       integer NOT NULL DEFAULT 1,
    value_string                  text,
    value_number                  numeric,
    value_boolean                 boolean,
    value_date                    date,
    value_timestamp               timestamptz,
    value_json                    jsonb,
    CONSTRAINT pk_edge_annotation PRIMARY KEY (edge_id, edge_attribute_definition_id, ordinal),
    CONSTRAINT ck_edge_annotation_value CHECK (
        value_string IS NOT NULL OR value_number IS NOT NULL OR value_boolean IS NOT NULL
        OR value_date IS NOT NULL OR value_timestamp IS NOT NULL OR value_json IS NOT NULL)
);

-- = REVISIONS =

CREATE TABLE IF NOT EXISTS vertex_revision (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenant (id),
    vertex_id   uuid NOT NULL REFERENCES vertex (id) ON DELETE CASCADE,
    revision    text NOT NULL,
    is_current  boolean NOT NULL DEFAULT TRUE,
    snapshot    jsonb,
    change_id   uuid REFERENCES vertex (id),
    created_by  uuid REFERENCES app_user (id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_vertex_revision UNIQUE (tenant_id, vertex_id, revision)
);

-- = LIFECYCLE =

CREATE TABLE IF NOT EXISTS lifecycle (
    id              uuid PRIMARY KEY,
    profile_id      text NOT NULL REFERENCES profile (profile_id),
    lifecycle_key   text NOT NULL,
    applies_to_type uuid REFERENCES vertex_type (id),
    CONSTRAINT uq_lifecycle_key UNIQUE (profile_id, lifecycle_key)
);

CREATE TABLE IF NOT EXISTS lifecycle_state (
    id            uuid PRIMARY KEY,
    lifecycle_id  uuid NOT NULL REFERENCES lifecycle (id) ON DELETE CASCADE,
    state_name    text NOT NULL,
    display_order integer NOT NULL DEFAULT 0,
    CONSTRAINT uq_lifecycle_state UNIQUE (lifecycle_id, state_name)
);

CREATE TABLE IF NOT EXISTS lifecycle_transition (
    id           uuid PRIMARY KEY,
    lifecycle_id uuid NOT NULL REFERENCES lifecycle (id) ON DELETE CASCADE,
    from_state   text NOT NULL,
    to_state     text NOT NULL,
    action       text,
    CONSTRAINT fk_lifecycle_transition_from FOREIGN KEY (lifecycle_id, from_state)
        REFERENCES lifecycle_state (lifecycle_id, state_name),
    CONSTRAINT fk_lifecycle_transition_to FOREIGN KEY (lifecycle_id, to_state)
        REFERENCES lifecycle_state (lifecycle_id, state_name)
);

-- = GRAPH QUERIES =

CREATE TABLE IF NOT EXISTS graph_query (
    id                uuid PRIMARY KEY,
    profile_id        text NOT NULL REFERENCES profile (profile_id),
    query_key         text NOT NULL,
    start_vertex_type uuid REFERENCES vertex_type (id),
    definition        jsonb NOT NULL,
    CONSTRAINT uq_graph_query_key UNIQUE (profile_id, query_key)
);

-- = WORKFLOW =

CREATE TABLE IF NOT EXISTS workflow_definition (
    id              uuid PRIMARY KEY,
    profile_id      text NOT NULL REFERENCES profile (profile_id),
    workflow_key    text NOT NULL,
    name            text,
    applies_to_type uuid REFERENCES vertex_type (id),
    trigger_action  text,
    definition      jsonb NOT NULL,
    CONSTRAINT uq_workflow_key UNIQUE (profile_id, workflow_key)
);

CREATE TABLE IF NOT EXISTS workflow_stage (
    id                 uuid PRIMARY KEY,
    workflow_id        uuid NOT NULL REFERENCES workflow_definition (id) ON DELETE CASCADE,
    stage_key          text NOT NULL,
    name               text,
    stage_type         text NOT NULL,
    display_order      integer NOT NULL DEFAULT 0,
    assignee_type      text,
    assignee_value     text,
    approvals_required integer,
    entry_graph_query  uuid REFERENCES graph_query (id),
    on_approve         text,
    on_reject          text,
    definition         jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_workflow_stage UNIQUE (workflow_id, stage_key)
);

CREATE TABLE IF NOT EXISTS workflow_instance (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL REFERENCES tenant (id),
    workflow_id   uuid NOT NULL REFERENCES workflow_definition (id),
    vertex_id     uuid NOT NULL REFERENCES vertex (id) ON DELETE CASCADE,
    current_stage uuid REFERENCES workflow_stage (id),
    status        text NOT NULL DEFAULT 'RUNNING',
    outcome       text,
    started_by    uuid REFERENCES app_user (id),
    started_at    timestamptz NOT NULL DEFAULT now(),
    completed_at  timestamptz
);

CREATE TABLE IF NOT EXISTS workflow_task (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id uuid NOT NULL REFERENCES workflow_instance (id) ON DELETE CASCADE,
    stage_id    uuid NOT NULL REFERENCES workflow_stage (id),
    assignee_id uuid REFERENCES app_user (id),
    status      text NOT NULL DEFAULT 'PENDING',
    decision    text,
    comment     text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    decided_at  timestamptz
);

-- = CONFIGURATION & AUDIT =

CREATE TABLE IF NOT EXISTS profile_section (
    profile_id text NOT NULL REFERENCES profile (profile_id),
    section    text NOT NULL,
    config     jsonb NOT NULL,
    CONSTRAINT pk_profile_section PRIMARY KEY (profile_id, section)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   uuid NOT NULL REFERENCES tenant (id),
    actor_id    uuid REFERENCES app_user (id),
    action      text NOT NULL,
    entity_type text NOT NULL,
    entity_id   text,
    details     jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- = CORE INDEXES =

CREATE INDEX IF NOT EXISTS ix_vertex_tenant_type ON vertex (tenant_id, vertex_type_id);
CREATE INDEX IF NOT EXISTS ix_vertex_lifecycle ON vertex (tenant_id, lifecycle_state);
CREATE INDEX IF NOT EXISTS ix_vertex_status ON vertex (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_vertex_name ON vertex (tenant_id, name);
CREATE INDEX IF NOT EXISTS ix_vertex_attribute_def ON vertex_attribute (attribute_definition_id);
CREATE INDEX IF NOT EXISTS ix_vertex_attribute_string ON vertex_attribute (value_string)
    WHERE value_string IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_vertex_attribute_number ON vertex_attribute (value_number)
    WHERE value_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_edge_tenant_type ON edge (tenant_id, edge_type_id);
CREATE INDEX IF NOT EXISTS ix_edge_source ON edge (source_vertex_id);
CREATE INDEX IF NOT EXISTS ix_edge_target ON edge (target_vertex_id);
CREATE INDEX IF NOT EXISTS ix_edge_status ON edge (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_edge_effectivity ON edge (effective_from, effective_to);
CREATE INDEX IF NOT EXISTS ix_edge_annotation_def ON edge_annotation (edge_attribute_definition_id);
CREATE INDEX IF NOT EXISTS ix_vertex_revision_current ON vertex_revision (tenant_id, vertex_id, is_current);
CREATE INDEX IF NOT EXISTS ix_workflow_instance_vertex ON workflow_instance (tenant_id, vertex_id);
CREATE INDEX IF NOT EXISTS ix_workflow_instance_status ON workflow_instance (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_workflow_task_assignee ON workflow_task (assignee_id, status);
CREATE INDEX IF NOT EXISTS ix_audit_log_entity ON audit_log (tenant_id, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_log_created ON audit_log (tenant_id, created_at);"""


def generate_schema_sql(profile: ResolvedProfile) -> str:
    """Return the full schema.sql (DDL + seed data) for a resolved profile."""
    parts = [_header(profile), _DDL, _seeds(profile)]
    return "\n\n".join(part.rstrip() + "\n" for part in parts)


def _header(profile: ResolvedProfile) -> str:
    inherited = " <- ".join(reversed(profile.inherits)) if profile.inherits else "(none)"
    return f"""\
-- AUTO-GENERATED BY PLM-IQ
-- DO NOT EDIT
-- Source: {profile.source_files[-1]}
-- Profile: {profile.profile_id} {profile.version} (inherits: {inherited})
-- Target: PostgreSQL 13+ (gen_random_uuid core function)
--
-- Idempotent: CREATE TABLE IF NOT EXISTS + seed rows upserted by stable keys.
-- Seed UUIDs are deterministic: md5('<profile>|<kind>|<key>')::uuid."""


def _lit(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return _lit(encoded) + "::jsonb"


def _uid(profile_id: str, kind: str, key: str) -> str:
    return f"md5({_lit(f'{profile_id}|{kind}|{key}')})::uuid"


def _values(rows: list[str]) -> str:
    return ",\n    ".join(rows)


def _ordered_vertex_types(profile: ResolvedProfile) -> list[dict[str, Any]]:
    types_by_id = profile.vertex_type_index()
    ordered: list[dict[str, Any]] = []
    visited: set[str] = set()

    def visit(vtype: dict[str, Any]) -> None:
        key = str(vtype["id"])
        if key in visited:
            return
        visited.add(key)
        parent = vtype.get("extends")
        if parent and str(parent) in types_by_id:
            visit(types_by_id[str(parent)])
        ordered.append(vtype)

    for vtype in profile.vertex_types:
        visit(vtype)
    return ordered


# ---------------------------------------------------------------- seeds


def _seeds(profile: ResolvedProfile) -> str:
    blocks = [
        _seed_profile(profile),
        _seed_vertex_types(profile),
        _seed_vertex_attributes(profile),
        _seed_edge_types(profile),
        _seed_edge_attributes(profile),
        _seed_lifecycles(profile),
        _seed_graph_queries(profile),
        _seed_workflows(profile),
        _seed_profile_sections(profile),
        _profile_indexes(profile),
    ]
    return (
        "-- ================================\n-- = SEED DATA (resolved profile) =\n-- ================================\n\n"
        + "\n\n".join(blocks)
    )


def _seed_profile(profile: ResolvedProfile) -> str:
    return f"""\
-- Profile
INSERT INTO profile (profile_id, name, version, inherits, source_files) VALUES
    ({_lit(profile.profile_id)}, {_lit(profile.name)}, {_lit(profile.version)},
     {_json(profile.inherits)}, {_json(profile.source_files)})
ON CONFLICT (profile_id) DO UPDATE SET
    name = EXCLUDED.name,
    version = EXCLUDED.version,
    inherits = EXCLUDED.inherits,
    source_files = EXCLUDED.source_files;"""


def _seed_vertex_types(profile: ResolvedProfile) -> str:
    rows = []
    for order, vtype in enumerate(_ordered_vertex_types(profile)):
        key = str(vtype["id"])
        abstract = bool(vtype.get("abstract"))
        rows.append(
            f"({_uid(profile.profile_id, 'vertex_type', key)}, {_lit(profile.profile_id)}, {_lit(key)}, "
            f"{_lit(str(vtype.get('label') or key.upper()))}, {_lit(vtype.get('extends'))}, "
            f"{_lit(abstract)}, {_lit(abstract)}, {order})"
        )
    return f"""\
-- Vertex types (abstract base first, then concrete types)
INSERT INTO vertex_type (id, profile_id, type_key, label, parent_key, is_abstract, is_system, display_order) VALUES
    {_values(rows)}
ON CONFLICT (profile_id, type_key) DO UPDATE SET
    label = EXCLUDED.label,
    parent_key = EXCLUDED.parent_key,
    is_abstract = EXCLUDED.is_abstract,
    is_system = EXCLUDED.is_system,
    display_order = EXCLUDED.display_order;"""


def _attribute_row(
    profile_id: str,
    kind_prefix: str,
    scope_key: str,
    prop: dict[str, Any],
    order: int,
    is_system: bool | None = None,
    is_structural: bool | None = None,
) -> str:
    name = str(prop["id"])
    data_type = str(prop.get("type", "string"))
    has_default = "default" in prop
    enum_values = _json(prop["values"]) if data_type == "enum" and prop.get("values") else "NULL"
    fields = [
        _uid(profile_id, kind_prefix, f"{scope_key}.{name}"),
        _lit(profile_id),
        _lit(scope_key),
        _lit(name),
        _lit(prop.get("label")),
        _lit(data_type),
        _lit(bool(prop.get("required"))),
        _json(prop["default"]) if has_default else "NULL",
        enum_values,
        _lit(prop.get("unit")),
        _lit(bool(prop.get("searchable"))),
        _lit(bool(prop.get("filterable"))),
        _lit(bool(prop.get("indexed"))),
    ]
    if is_system is not None:
        fields.append(_lit(is_system))
    if is_structural is not None:
        fields.append(_lit(is_structural))
    fields.append(str(order))
    return "(" + ", ".join(fields) + ")"


def _seed_vertex_attributes(profile: ResolvedProfile) -> str:
    types_by_id = profile.vertex_type_index()
    rows = []
    for vtype in _ordered_vertex_types(profile):
        type_key = str(vtype["id"])
        for order, prop in enumerate(effective_properties(vtype, types_by_id)):
            rows.append(
                _attribute_row(
                    profile.profile_id,
                    "attribute_definition",
                    type_key,
                    prop,
                    order,
                    is_system=bool(prop.get("system")),
                    is_structural=bool(prop.get("_structural")),
                )
            )
    return f"""\
-- Vertex attribute definitions (structural envelope properties flagged is_structural)
INSERT INTO attribute_definition (
    id, profile_id, vertex_type_key, name, label, data_type, required, default_value,
    enum_values, unit, searchable, filterable, indexed, is_system, is_structural, display_order)
VALUES
    {_values(rows)}
ON CONFLICT (profile_id, vertex_type_key, name) DO UPDATE SET
    label = EXCLUDED.label,
    data_type = EXCLUDED.data_type,
    required = EXCLUDED.required,
    default_value = EXCLUDED.default_value,
    enum_values = EXCLUDED.enum_values,
    unit = EXCLUDED.unit,
    searchable = EXCLUDED.searchable,
    filterable = EXCLUDED.filterable,
    indexed = EXCLUDED.indexed,
    is_system = EXCLUDED.is_system,
    is_structural = EXCLUDED.is_structural,
    display_order = EXCLUDED.display_order;"""


def _seed_edge_types(profile: ResolvedProfile) -> str:
    rows = []
    for etype in profile.edge_types:
        key = str(etype["id"])
        rows.append(
            f"({_uid(profile.profile_id, 'edge_type', key)}, {_lit(profile.profile_id)}, {_lit(key)}, "
            f"{_lit(str(etype.get('label') or key.upper()))}, {_lit(etype.get('description'))}, "
            f"{_lit(str(etype['source']))}, {_lit(str(etype['target']))}, "
            f"{_lit(bool(etype.get('directed', True)))}, {_lit(bool(etype.get('symmetric', False)))}, "
            f"{_json(etype.get('constraints') or {})})"
        )
    return f"""\
-- Edge types
INSERT INTO edge_type (
    id, profile_id, edge_key, label, description, source_type_key, target_type_key,
    directed, is_symmetric, constraint_rules)
VALUES
    {_values(rows)}
ON CONFLICT (profile_id, edge_key) DO UPDATE SET
    label = EXCLUDED.label,
    description = EXCLUDED.description,
    source_type_key = EXCLUDED.source_type_key,
    target_type_key = EXCLUDED.target_type_key,
    directed = EXCLUDED.directed,
    is_symmetric = EXCLUDED.is_symmetric,
    constraint_rules = EXCLUDED.constraint_rules;"""


def _seed_edge_attributes(profile: ResolvedProfile) -> str:
    rows = []
    for etype in profile.edge_types:
        edge_key = str(etype["id"])
        for order, prop in enumerate(etype.get("properties") or []):
            rows.append(_attribute_row(profile.profile_id, "edge_attribute_definition", edge_key, prop, order))
    if not rows:
        return "-- Edge attribute definitions\n-- (none defined)\n"
    return f"""\
-- Edge attribute definitions (edge annotations)
INSERT INTO edge_attribute_definition (
    id, profile_id, edge_type_key, name, label, data_type, required, default_value,
    enum_values, unit, searchable, filterable, indexed, display_order)
VALUES
    {_values(rows)}
ON CONFLICT (profile_id, edge_type_key, name) DO UPDATE SET
    label = EXCLUDED.label,
    data_type = EXCLUDED.data_type,
    required = EXCLUDED.required,
    default_value = EXCLUDED.default_value,
    enum_values = EXCLUDED.enum_values,
    unit = EXCLUDED.unit,
    searchable = EXCLUDED.searchable,
    filterable = EXCLUDED.filterable,
    indexed = EXCLUDED.indexed,
    display_order = EXCLUDED.display_order;"""


def _seed_lifecycles(profile: ResolvedProfile) -> str:
    blocks = []
    for lifecycle in profile.lifecycles:
        key = lifecycle["key"]
        lc_uid = _uid(profile.profile_id, "lifecycle", key)
        applies = (
            _uid(profile.profile_id, "vertex_type", lifecycle["applies_to"]) if lifecycle["applies_to"] else "NULL"
        )
        states = {state: _uid(profile.profile_id, "lifecycle_state", f"{key}.{state}") for state in lifecycle["states"]}
        state_rows = [
            f"({states[state]}, {lc_uid}, {_lit(state)}, {order})" for order, state in enumerate(lifecycle["states"])
        ]
        transition_rows = []
        for transition in lifecycle["transitions"]:
            action = str(transition.get("action") or "")
            tid = _uid(
                profile.profile_id, "lifecycle_transition", f"{key}.{transition['from']}.{transition['to']}.{action}"
            )
            transition_rows.append(
                f"({tid}, {lc_uid}, {_lit(transition['from'])}, {_lit(transition['to'])}, {_lit(action)})"
            )
        blocks.append(
            f"""\
-- Lifecycle '{key}'
INSERT INTO lifecycle (id, profile_id, lifecycle_key, applies_to_type) VALUES
    ({lc_uid}, {_lit(profile.profile_id)}, {_lit(key)}, {applies})
ON CONFLICT (profile_id, lifecycle_key) DO UPDATE SET
    applies_to_type = EXCLUDED.applies_to_type;

INSERT INTO lifecycle_state (id, lifecycle_id, state_name, display_order) VALUES
    {_values(state_rows)}
ON CONFLICT (lifecycle_id, state_name) DO UPDATE SET
    display_order = EXCLUDED.display_order;

INSERT INTO lifecycle_transition (id, lifecycle_id, from_state, to_state, action) VALUES
    {_values(transition_rows)}
ON CONFLICT (id) DO UPDATE SET
    from_state = EXCLUDED.from_state,
    to_state = EXCLUDED.to_state,
    action = EXCLUDED.action;"""
        )
    return "\n\n".join(blocks) if blocks else "-- Lifecycles\n-- (none defined)\n"


def _seed_graph_queries(profile: ResolvedProfile) -> str:
    rows = []
    for query in profile.graph_queries:
        query_id = str(query["id"])
        start = query.get("start_vertex")
        start_uid = _uid(profile.profile_id, "vertex_type", str(start)) if start else "NULL"
        definition = {k: v for k, v in query.items() if k != "id"}
        rows.append(
            f"({_uid(profile.profile_id, 'graph_query', query_id)}, {_lit(profile.profile_id)}, "
            f"{_lit(query_id)}, {start_uid}, {_json(definition)})"
        )
    if not rows:
        return "-- Graph queries\n-- (none defined)\n"
    return f"""\
-- Graph queries
INSERT INTO graph_query (id, profile_id, query_key, start_vertex_type, definition) VALUES
    {_values(rows)}
ON CONFLICT (profile_id, query_key) DO UPDATE SET
    start_vertex_type = EXCLUDED.start_vertex_type,
    definition = EXCLUDED.definition;"""


def _seed_workflows(profile: ResolvedProfile) -> str:
    blocks = []
    for workflow in profile.workflows:
        wf_id = str(workflow["id"])
        wf_uid = _uid(profile.profile_id, "workflow_definition", wf_id)
        applies = workflow.get("applies_to")
        applies_uid = _uid(profile.profile_id, "vertex_type", str(applies)) if applies else "NULL"
        trigger = workflow.get("trigger")
        trigger_action = trigger if isinstance(trigger, str) or trigger is None else json.dumps(trigger)
        definition = {k: v for k, v in workflow.items() if k != "stages"}
        stage_rows = []
        for order, stage in enumerate(workflow.get("stages") or []):
            stage_id = str(stage["id"])
            assignee = stage.get("assignee") or {}
            entry = stage.get("entry_graph_query")
            entry_uid = _uid(profile.profile_id, "graph_query", str(entry)) if entry else "NULL"
            approvals = stage.get("approvals_required")
            stage_rows.append(
                f"({_uid(profile.profile_id, 'workflow_stage', f'{wf_id}.{stage_id}')}, {wf_uid}, "
                f"{_lit(stage_id)}, {_lit(stage.get('name'))}, {_lit(str(stage.get('type', 'approval')))}, "
                f"{order}, {_lit(assignee.get('type'))}, {_lit(assignee.get('value'))}, "
                f"{approvals if approvals is not None else 'NULL'}, {entry_uid}, "
                f"{_lit(stage.get('on_approve'))}, {_lit(stage.get('on_reject'))}, {_json(stage)})"
            )
        blocks.append(
            f"""\
-- Workflow '{wf_id}'
INSERT INTO workflow_definition (id, profile_id, workflow_key, name, applies_to_type, trigger_action, definition) VALUES
    ({wf_uid}, {_lit(profile.profile_id)}, {_lit(wf_id)}, {_lit(workflow.get("name"))},
     {applies_uid}, {_lit(trigger_action)}, {_json(definition)})
ON CONFLICT (profile_id, workflow_key) DO UPDATE SET
    name = EXCLUDED.name,
    applies_to_type = EXCLUDED.applies_to_type,
    trigger_action = EXCLUDED.trigger_action,
    definition = EXCLUDED.definition;

INSERT INTO workflow_stage (
    id, workflow_id, stage_key, name, stage_type, display_order, assignee_type,
    assignee_value, approvals_required, entry_graph_query, on_approve, on_reject, definition)
VALUES
    {_values(stage_rows)}
ON CONFLICT (workflow_id, stage_key) DO UPDATE SET
    name = EXCLUDED.name,
    stage_type = EXCLUDED.stage_type,
    display_order = EXCLUDED.display_order,
    assignee_type = EXCLUDED.assignee_type,
    assignee_value = EXCLUDED.assignee_value,
    approvals_required = EXCLUDED.approvals_required,
    entry_graph_query = EXCLUDED.entry_graph_query,
    on_approve = EXCLUDED.on_approve,
    on_reject = EXCLUDED.on_reject,
    definition = EXCLUDED.definition;"""
        )
    return "\n\n".join(blocks) if blocks else "-- Workflows\n-- (none defined)\n"


def _seed_profile_sections(profile: ResolvedProfile) -> str:
    rows = [
        f"({_lit(profile.profile_id)}, {_lit(name)}, {_json(config)})"
        for name, config in sorted(profile.config_sections.items())
    ]
    if not rows:
        return "-- Profile configuration sections\n-- (none defined)\n"
    return f"""\
-- Profile configuration sections (terminology, revision, search, ai, ui, configuration)
INSERT INTO profile_section (profile_id, section, config) VALUES
    {_values(rows)}
ON CONFLICT (profile_id, section) DO UPDATE SET
    config = EXCLUDED.config;"""


def _profile_indexes(profile: ResolvedProfile) -> str:
    statements: list[str] = []
    types_by_id = profile.vertex_type_index()
    for vtype in _ordered_vertex_types(profile):
        if vtype.get("abstract"):
            continue
        type_key = str(vtype["id"])
        for prop in effective_properties(vtype, types_by_id):
            statement = _prop_index_statement("ix_vattr", f"vattr_{type_key}", prop, "vertex_attribute")
            if statement:
                statements.append(statement)
    for etype in profile.edge_types:
        edge_key = str(etype["id"])
        for prop in etype.get("properties") or []:
            statement = _prop_index_statement("ix_eann", f"eann_{edge_key}", prop, "edge_annotation")
            if statement:
                statements.append(statement)
    body = "\n".join(statements) if statements else "-- (no profile-specific attribute indexes)"
    return "-- Profile-specific attribute indexes (indexed/searchable/filterable properties)\n" + body


def _prop_index_statement(prefix: str, context: str, prop: dict[str, Any], table: str) -> str | None:
    if not (prop.get("indexed") or prop.get("searchable") or prop.get("filterable")):
        return None
    column = _VALUE_COLUMN[str(prop.get("type", "string"))]
    suffix = _INDEX_SUFFIX.get(column)
    if suffix is None:
        return None
    return f"CREATE INDEX IF NOT EXISTS {prefix}_{context}_{prop['id']}_{suffix} ON {table} (attribute_definition_id, {column});"

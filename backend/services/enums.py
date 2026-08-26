"""Python mirrors of the PostgreSQL enums declared in database/schema/*.sql."""
from __future__ import annotations

from enum import Enum


class VertexKind(str, Enum):
    VERTEX = "Vertex"
    NODE = "Item"
    DOCUMENT = "Document"
    EC = "EC"


class EditionId(str, Enum):
    FOUNDATION = "foundation"
    DISCRETE = "discrete"
    PROCESS = "process"
    FOOD = "food"


class LifecycleState(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    RELEASED = "released"
    SUPERSEDED = "superseded"
    OBSOLETE = "obsolete"


class EdgeKind(str, Enum):
    BOM = "BOM"
    REFDOCS = "REFDOCS"
    USES = "USES"
    MANUFACTURED_BY = "MANUFACTURED_BY"
    SUPPLIED_BY = "SUPPLIED_BY"
    AFFECTS = "AFFECTS"
    SUPERSEDES = "SUPERSEDES"
    ALTERNATE_FOR = "ALTERNATE_FOR"
    SUBSTITUTE_FOR = "SUBSTITUTE_FOR"
    COMPLIES_WITH = "COMPLIES_WITH"
    CONTAINS = "CONTAINS"
    VALIDATED_BY = "VALIDATED_BY"
    PACKAGED_IN = "PACKAGED_IN"
    HAS_LABEL = "HAS_LABEL"


class EdgeState(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    INACTIVE = "inactive"


class RuleScope(str, Enum):
    PLATFORM = "platform"
    EDITION = "edition"
    TENANT = "tenant"


class Cardinality(str, Enum):
    ZERO_OR_ONE = "0..1"
    EXACTLY_ONE = "1..1"
    ZERO_OR_MANY = "0..N"
    ONE_OR_MANY = "1..N"


class Participation(str, Enum):
    OPTIONAL = "optional"
    REQUIRED_FOR_RELEASE = "required_for_release"


class RuleDirection(str, Enum):
    SOURCE_TO_TARGET = "source_to_target"


class TenantStatus(str, Enum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


class RoleScope(str, Enum):
    GLOBAL = "global"
    TENANT = "tenant"


class SettingLevel(str, Enum):
    PLATFORM = "platform"
    TENANT = "tenant"
    USER = "user"

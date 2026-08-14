"""SQLAlchemy models for all PLM entities."""

from app.models.tenant_user import Tenant, User
from app.models.parts import Part
from app.models.bom import BomItem
from app.models.costing import CostingBomItem
from app.models.eco import EngineeringChangeOrder
from app.models.aml import ApprovedManufacturer
from app.models.avl import ApprovedVendor
from app.models.cad import CadMetadata
from app.models.documents import Document
from app.models.queries import SavedQuery
from app.models.workflow import WorkflowDefinition, WorkflowInstance, WorkflowTask, Notification
from app.models.role import Role, role_names
from app.models.favorite import Favorite
from app.models.setting import AppSetting
from app.models.graph import (
    GraphNode,
    GraphEdgeType,
    GraphEdge,
    GraphEdgeAnnotation,
    GraphEdgeEvidence,
    GraphEdgeImpact,
)

__all__ = [
    "Tenant",
    "User",
    "Part",
    "BomItem",
    "CostingBomItem",
    "EngineeringChangeOrder",
    "ApprovedManufacturer",
    "ApprovedVendor",
    "CadMetadata",
    "Document",
    "SavedQuery",
    "WorkflowDefinition",
    "WorkflowInstance",
    "WorkflowTask",
    "Notification",
    "Role",
    "role_names",
    "Favorite",
    "AppSetting",
    "GraphNode",
    "GraphEdgeType",
    "GraphEdge",
    "GraphEdgeAnnotation",
    "GraphEdgeEvidence",
    "GraphEdgeImpact",
]

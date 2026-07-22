"""Role catalog model.

Roles are a global, admin-managed vocabulary. Each `User` (and `Tenant`) carries a single
`role` string that must match a `Role.name` from this catalog. The workflow engine resolves
step assignees by matching `User.role == step.assignee`, so the catalog is what makes role
names discoverable in the user/tenant/template dropdowns.
"""

from sqlalchemy import Column, Integer, String
from app.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)  # lowercase identifier
    description = Column(String)
    created_at = Column(String)


def role_names(db) -> list:
    """Return all role names ordered alphabetically."""
    return [r.name for r in db.query(Role).order_by(Role.name).all()]


def role_rows(db) -> list:
    """Return roles as dicts with their current user count (for admin UIs)."""
    from app.models.tenant_user import User
    rows = []
    for r in db.query(Role).order_by(Role.name).all():
        user_count = db.query(User).filter(User.role == r.name).count()
        rows.append({
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "user_count": user_count,
        })
    return rows

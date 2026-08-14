"""Tenant and User models."""

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column("tenant_id", Integer, primary_key=True, autoincrement=True)
    tenant_name = Column("tenant_name", String, unique=True, nullable=False)
    tenant_key = Column("tenant_key", String, unique=True, nullable=False)
    tenant_secret = Column("tenant_secret", String, nullable=False, default="")
    subdomain = Column("subdomain", String, unique=True, nullable=True)
    description = Column("description", String)
    created_date = Column("created_date", String)
    role = Column("role", String, default="reader")
    is_active = Column("is_active", Boolean, default=True)

    # Per-tenant Gitea separation (see docs/multitenant-gitea.md).
    git_username = Column("git_username", String, nullable=True)          # per-tenant Gitea user (owner of its repos)
    git_secret_enc = Column("git_secret_enc", String, nullable=True)      # Fernet-encrypted Gitea password/token
    git_cad_repo = Column("git_cad_repo", String, nullable=True)          # tenant's private CAD repo
    git_docs_repo = Column("git_docs_repo", String, nullable=True)        # tenant's private docs repo
    git_provisioned = Column("git_provisioned", Boolean, default=False)   # idempotent provisioning flag
    node_id = Column("node_id", Integer, ForeignKey("plmiq_node.node_id"))

    node = relationship("GraphNode")

    users = relationship("User", back_populates="tenant")
    parts = relationship("Part", back_populates="tenant")
    favorites = relationship("Favorite", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    user_id = Column("user_id", Integer, primary_key=True, autoincrement=True)
    username = Column("username", String, unique=True, nullable=True)
    full_name = Column("full_name", String, nullable=False)
    email = Column("email", String, unique=True, nullable=False)
    email_verified = Column("email_verified", Boolean, nullable=False, default=False)
    password_hash = Column("password_hash", String, nullable=False, default="")
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)
    is_active = Column("is_active", Boolean, default=True)
    created_date = Column("created_date", String)
    role = Column("role", String, nullable=False, default="reader")
    node_id = Column("node_id", Integer, ForeignKey("plmiq_node.node_id"))

    node = relationship("GraphNode")

    tenant = relationship("Tenant", back_populates="users")
    favorites = relationship("Favorite", back_populates="user")

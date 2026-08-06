"""Tenant and User models."""

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column("tenant_id", Integer, primary_key=True, autoincrement=True)
    tenant_name = Column("tenant_name", String, unique=True, nullable=False)
    tenant_key = Column("tenant_key", String, unique=True, nullable=False)
    subdomain = Column("subdomain", String, unique=True, nullable=True)
    description = Column("description", String)
    created_date = Column("created_date", String)
    role = Column("role", String, default="reader")
    is_active = Column("is_active", Boolean, default=True)

    users = relationship("User", back_populates="tenant")
    parts = relationship("Part", back_populates="tenant")
    favorites = relationship("Favorite", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    user_id = Column("user_id", Integer, primary_key=True, autoincrement=True)
    username = Column("username", String, unique=True, nullable=False)
    full_name = Column("full_name", String, nullable=False)
    email = Column("email", String)
    password_hash = Column("password_hash", String, nullable=False, default="")
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)
    is_active = Column("is_active", Boolean, default=True)
    created_date = Column("created_date", String)
    role = Column("role", String, default="reader")

    tenant = relationship("Tenant", back_populates="users")
    favorites = relationship("Favorite", back_populates="user")

"""AppSetting model — per-tenant key-value store for app-level configuration.

The tenant with ``tenant_key == GLOBAL_TENANT_KEY`` (``plm-iq``) holds the
global defaults; every other tenant's rows override them. See ``app/settings.py``
for the resolution logic.
"""

from sqlalchemy import Column, String
from app.database import Base

GLOBAL_TENANT_KEY = "plm-iq"


class AppSetting(Base):
    """Application setting (key-value pair, like a .env managed from the UI)."""
    __tablename__ = "app_settings"

    tenant_key = Column("tenant_key", String, primary_key=True, default=GLOBAL_TENANT_KEY)
    key = Column("key", String, primary_key=True)
    value = Column("value", String, nullable=False, default="")

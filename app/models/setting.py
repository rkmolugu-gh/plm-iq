"""AppSetting model — key-value store for app-level configuration."""

from sqlalchemy import Column, String
from app.database import Base


class AppSetting(Base):
    """Application setting (key-value pair, like a .env managed from the UI)."""
    __tablename__ = "app_settings"

    key = Column("key", String, primary_key=True)
    value = Column("value", String, nullable=False, default="")

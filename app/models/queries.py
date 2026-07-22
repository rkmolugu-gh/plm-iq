"""Saved query / report model."""

from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from app.database import Base


class SavedQuery(Base):
    """A saved query the user can re-run and export as a report.

    `mode` is either "guided" (definition holds a JSON builder config) or
    "sql" (definition holds a raw SQL string executed read-only).
    """

    __tablename__ = "saved_queries"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    name = Column("name", String, nullable=False)
    description = Column("description", String)
    mode = Column("mode", String, nullable=False, default="guided")  # "guided" | "sql"
    definition = Column("definition", Text, nullable=False)  # JSON config or raw SQL
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"), nullable=False)
    created_at = Column("created_at", String)
    is_public = Column("is_public", Boolean, default=False)

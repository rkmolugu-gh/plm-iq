"""Object ID sequence model — per-tenant, race-safe auto-numbering.

Each row tracks the current counter for one ``obj_type`` in one tenant. The
``prefix`` is denormalised from the tenant's effective settings so the generated id
(e.g. ``PLM-001``) always reflects the prefix in force. ``value`` is the next
number to use; it is advanced atomically (single row UPDATE ... RETURNING) so
concurrent creates never receive the same id twice.
"""

from sqlalchemy import Column, Integer, String

from app.database import Base


class IdSequence(Base):
    __tablename__ = "id_sequences"

    tenant_key = Column("tenant_key", String, primary_key=True)
    obj_type = Column("obj_type", String, primary_key=True)
    prefix = Column("prefix", String, nullable=False, default="")
    value = Column("value", Integer, nullable=False, default=1)

    def __repr__(self):
        return f"<IdSequence tenant={self.tenant_key} {self.obj_type}={self.prefix}{self.value}>"

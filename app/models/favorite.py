"""
Favorites model for bookmarking Parts, Documents, and ECOs.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    object_type = Column(String(20), nullable=False)  # 'part', 'document', 'eco'
    object_id = Column(String, nullable=False)  # part_number, document id, or eco_number
    created_date = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d"))
    tenant_id = Column(String, ForeignKey("tenants.tenant_id"), nullable=False)

    # Relationships
    user = relationship("User", back_populates="favorites")
    tenant = relationship("Tenant", back_populates="favorites")

    # Unique constraint to prevent duplicate favorites
    __table_args__ = (
        UniqueConstraint('user_id', 'object_type', 'object_id', name='uq_user_object_favorite'),
    )

    def __repr__(self):
        return f"<Favorite(user={self.user_id}, type={self.object_type}, id={self.object_id})>"

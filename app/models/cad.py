"""CAD Metadata model."""

from sqlalchemy import Column, Integer, String, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class CadMetadata(Base):
    __tablename__ = "cad_metadata"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    number = Column("number", String, nullable=True)
    part_number = Column("part_number", String, ForeignKey("parts.part_number"), nullable=False)
    part_revision = Column("part_revision", String)
    part_name = Column("part_name", String)
    status = Column("status", String)
    cad_file_name = Column("cad_file_name", String, nullable=False)
    cad_file_format = Column("cad_file_format", String, nullable=False)
    cad_system = Column("cad_system", String)
    cad_version = Column("cad_version", String)
    file_reference_type = Column("file_reference_type", String, nullable=False)
    file_reference_url = Column("file_reference_url", String)
    git_repo_path = Column("git_repo_path", String)
    git_commit_sha = Column("git_commit_sha", String)
    git_manifest = Column("git_manifest", String)
    file_size_bytes = Column("file_size_bytes", BigInteger)
    file_checksum = Column("file_checksum", String)
    modeling_author = Column("modeling_author", Integer, ForeignKey("users.user_id"))
    cad_created_date = Column("cad_created_date", String)
    cad_modified_date = Column("cad_modified_date", String)
    drawing_number = Column("drawing_number", String)
    model_type = Column("model_type", String)
    source_type = Column("source_type", String)
    notes = Column("notes", String)
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    modified_by = Column("modified_by", Integer, ForeignKey("users.user_id"))
    created_date = Column("created_date", String)
    modified_date = Column("modified_date", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)
    node_id = Column("node_id", Integer, ForeignKey("plmiq_node.node_id"))

    node = relationship("GraphNode")

    part = relationship("Part", back_populates="cad_files")

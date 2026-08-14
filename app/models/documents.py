"""Document model for the standalone Document Management System.

Documents are stored in a Git repo (Gitea), hidden from the user. The table is
self-referential so folders can contain files and subfolders, forming a
hierarchy. The `kind` column ("file" | "folder") lets metadata distinguish a
folder (a container) from a file (which has content in Git).
"""

from sqlalchemy import Column, Integer, String, BigInteger, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    parent_id = Column("parent_id", Integer, ForeignKey("documents.id"), nullable=True)
    kind = Column("kind", String, nullable=False, default="file")  # "file" | "folder"
    name = Column("name", String, nullable=False)
    title = Column("title", String)
    doc_category = Column("doc_category", String)
    doc_format = Column("doc_format", String)
    doc_system = Column("doc_system", String)
    doc_version = Column("doc_version", String, default="1.0")
    status = Column("status", String, default="DRAFT")
    description = Column("description", Text)
    file_size_bytes = Column("file_size_bytes", BigInteger)
    file_checksum = Column("file_checksum", String)
    git_repo_path = Column("git_repo_path", String)
    git_commit_sha = Column("git_commit_sha", String)
    git_manifest = Column("git_manifest", Text)
    storage_backend = Column("storage_backend", String, default="Gitea")
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    modified_by = Column("modified_by", Integer, ForeignKey("users.user_id"))
    created_date = Column("created_date", String)
    modified_date = Column("modified_date", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)
    node_id = Column("node_id", Integer, ForeignKey("plmiq_node.node_id"))

    node = relationship("GraphNode")

    # Self-referential: a document's parent (None at the root) and its children.
    parent = relationship("Document", remote_side=[id], backref="children")

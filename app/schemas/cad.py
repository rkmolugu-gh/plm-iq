"""CAD Metadata schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class CadOut(BaseModel):
    id: int
    part_number: str
    part_revision: Optional[str] = None
    part_name: Optional[str] = None
    status: Optional[str] = None
    cad_file_name: str
    cad_file_format: str
    cad_system: Optional[str] = None
    cad_version: Optional[str] = None
    file_reference_type: str
    file_reference_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_checksum: Optional[str] = None
    modeling_author: Optional[int] = None
    cad_created_date: Optional[str] = None
    cad_modified_date: Optional[str] = None
    drawing_number: Optional[str] = None
    model_type: Optional[str] = None
    source_type: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

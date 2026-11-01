"""Response shapes of the Document Access page (DOC-ACCESS-SIMPLE, DAS-BE-9 .. DAS-BE-11)."""
from typing import Dict, List, Optional

from pydantic import BaseModel


class DocumentAccessCode(BaseModel):
    code: str
    name: str


class DocumentAccessCompany(BaseModel):
    id: str
    name: str


class DocumentAccessContact(BaseModel):
    id: str
    name: Optional[str] = None
    runs_as: str
    agent_on: bool
    access_types: List[str]
    companies: List[DocumentAccessCompany]
    blocked: Optional[str] = None


class DocumentAccessPreview(BaseModel):
    verdict: str
    reads: int
    total: int
    no_shared_code: int
    other_company: int


class DocumentAccessRow(BaseModel):
    id: str
    type_name: str
    is_shared: bool
    is_direct_access: bool
    grant_count: int
    file_count: int
    readable_count: int
    ai_read_staff: bool
    ai_read_codes: List[str]
    reach: Dict[str, int]
    preview: Optional[DocumentAccessPreview] = None


class DocumentAccessResponse(BaseModel):
    access_types: List[DocumentAccessCode]
    contact: Optional[DocumentAccessContact] = None
    rows: List[DocumentAccessRow]


class DocumentAccessDocument(BaseModel):
    id: str
    original_filename: str
    access_levels: List[str]
    company_name: Optional[str] = None
    ai_read_status: Optional[str] = None
    verdict: Optional[str] = None


class DocumentAccessDocumentsResponse(BaseModel):
    items: List[DocumentAccessDocument]
    total: int
    page: int
    limit: int

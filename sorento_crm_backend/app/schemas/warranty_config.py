"""Request bodies for the warranty configuration API (after-sales P2).

Responses are plain dicts built by ``warranty_config_service`` so the wire shape lives in one place.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class PolicyCreate(BaseModel):
    version: str
    effective_from: date
    effective_to: Optional[date] = None
    policy_text: Optional[str] = None


class PolicyUpdate(BaseModel):
    version: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    policy_text: Optional[str] = None


class SupersedeRequest(BaseModel):
    version: str
    effective_from: date
    policy_text: Optional[str] = None


class TermCreate(BaseModel):
    policy_id: str
    kind_id: str
    part_name: str
    duration_months: Optional[int] = None
    is_lifetime: bool = False
    covered_defect_type_ids: Optional[List[str]] = None
    installation_included: bool = False
    qualifications: Optional[str] = None
    exclusions: Optional[str] = None


class TermUpdate(BaseModel):
    part_name: Optional[str] = None
    duration_months: Optional[int] = None
    is_lifetime: Optional[bool] = None
    covered_defect_type_ids: Optional[List[str]] = None
    installation_included: Optional[bool] = None
    qualifications: Optional[str] = None
    exclusions: Optional[str] = None


class KindCreate(BaseModel):
    code: str
    name: str
    sort_order: int = 0
    is_active: bool = True


class KindUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class KindRuleCreate(BaseModel):
    kind_id: str
    match_type: str
    match_value: str
    priority: int = 0


class KindRuleUpdate(BaseModel):
    kind_id: Optional[str] = None
    match_type: Optional[str] = None
    match_value: Optional[str] = None
    priority: Optional[int] = None


class KindRuleTestRequest(BaseModel):
    product_id: str

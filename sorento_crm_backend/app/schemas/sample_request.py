"""Sample request write payloads (SR-CORE). Staff and portal share them.

Every field is optional on a draft; the submit rules live in `sample_request_service`.
Responses are plain dicts built by the service (list rows and detail differ on purpose:
list rows never carry the site contact phone or the ship-to address, AC-SR-54).
"""
from __future__ import annotations

from datetime import date as Date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SampleRequestLineIn(BaseModel):
    product_id: str
    qty: int = Field(1, ge=1)
    remark: Optional[str] = Field(None, max_length=255)


class SampleRequestWrite(BaseModel):
    customer_id: Optional[str] = None
    customer_name: Optional[str] = Field(None, max_length=255)
    project_id: Optional[str] = None
    project_title: Optional[str] = Field(None, max_length=255)
    quotation_document_id: Optional[str] = None
    quotation_issue_id: Optional[str] = None
    scope_note: Optional[str] = Field(None, max_length=255)
    delivery_date: Optional[Date] = None
    delivery_mode: Optional[Literal["driver", "self_deliver", "self_collect"]] = None
    #: SAMPLE-REQUEST-V2: the ship-to party; a party not on the project yet is linked in
    #: `ship_to_role`. `ship_to_contact_ids` are that party's people: their names fill the contact
    #: person ("A & B"), the phone is the first one's, and they join the project's stakeholders.
    ship_to_party_id: Optional[str] = Field(None, max_length=64)
    ship_to_role: Optional[str] = Field(None, max_length=32)
    ship_to_contact_ids: Optional[List[str]] = Field(None, max_length=20)
    ship_to_name: Optional[str] = Field(None, max_length=255)
    ship_to_address: Optional[str] = None
    site_contact_name: Optional[str] = Field(None, max_length=255)
    site_contact_phone: Optional[str] = Field(None, max_length=60)
    site_contact_note: Optional[str] = Field(None, max_length=255)
    loan_value: Optional[int] = Field(None, ge=1)
    loan_unit: Optional[Literal["days", "months"]] = None
    goods_from: Optional[Literal["demo", "new", "either"]] = None
    purpose: Optional[str] = None
    board_mounting: Optional[bool] = None
    board_label: Optional[str] = Field(None, max_length=255)
    lines: Optional[List[SampleRequestLineIn]] = None


class SampleRequestMove(BaseModel):
    to: str
    date: Optional[Date] = None
    reason: Optional[str] = None
    #: Start processing only (PS-SAMPLE-TRACKING rule 2).
    date_feasible: Optional[bool] = None
    proposed_delivery_date: Optional[Date] = None
    date_note: Optional[str] = Field(None, max_length=255)


class SampleRequestConsignmentLink(BaseModel):
    #: The AutoCount consignment (`sales_orders.id`, doc_type consignment); null unlinks.
    consignment_order_id: Optional[str] = None


class SampleRequestDateAnswer(BaseModel):
    date_feasible: Optional[bool] = None
    proposed_delivery_date: Optional[Date] = None
    date_note: Optional[str] = Field(None, max_length=255)


class SampleRequestInternal(BaseModel):
    consignment_no: Optional[str] = Field(None, max_length=80)
    po_no: Optional[str] = Field(None, max_length=80)

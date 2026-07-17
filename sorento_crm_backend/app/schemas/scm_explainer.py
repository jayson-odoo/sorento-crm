"""SCM M5 — semantic explainer request/response schemas (bounded LLM flow)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExplanationResult(BaseModel):
    explanation: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


class AskResult(BaseModel):
    answer: str


class AdvisoryResult(BaseModel):
    advisory: Optional[str] = None


class RunOverviewResult(BaseModel):
    overview: str

"""Schemas for composer message snippets (UAC AC-L4)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _clean(value):
    return value.strip() if isinstance(value, str) else value


class MessageSnippetBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    # The "/" keyword. Optional - a snippet is findable by name alone. Stored
    # without the leading slash: the slash is composer syntax, not part of the
    # keyword, and storing "/stock" would make "//stock" the way to reach it.
    shortcut: Optional[str] = Field(default=None, max_length=60)
    body: str = Field(min_length=1)
    is_active: bool = True

    @field_validator("name", "shortcut", "body", mode="before")
    @classmethod
    def _strip(cls, v):
        return _clean(v)

    @field_validator("shortcut", mode="after")
    @classmethod
    def _normalise_shortcut(cls, v):
        if v is None:
            return None
        v = v.lstrip("/").strip()
        return v or None


class MessageSnippetCreate(MessageSnippetBase):
    pass


class MessageSnippetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    shortcut: Optional[str] = Field(default=None, max_length=60)
    body: Optional[str] = Field(default=None, min_length=1)
    is_active: Optional[bool] = None

    @field_validator("name", "shortcut", "body", mode="before")
    @classmethod
    def _strip(cls, v):
        return _clean(v)

    @field_validator("shortcut", mode="after")
    @classmethod
    def _normalise_shortcut(cls, v):
        if v is None:
            return None
        v = v.lstrip("/").strip()
        return v or None


class MessageSnippetResponse(MessageSnippetBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MessageSnippetOption(BaseModel):
    """One row of the composer's "/" picker.

    ``body`` is the stored wording with its ``$tokens`` intact (what the admin
    typed); ``resolved_body`` is the same text with the ticket's context already
    substituted. The composer inserts ``resolved_body`` and shows ``body`` only
    as the preview, so what lands in the input is what the contact will read.
    """

    id: str
    name: str
    shortcut: Optional[str] = None
    body: str
    resolved_body: str

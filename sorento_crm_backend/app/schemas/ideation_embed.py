"""Ideation embed-session mint schemas (Ideas iframe SSO, §5.3, AC-42)."""
from pydantic import BaseModel, Field


class IdeationEmbedSessionRequest(BaseModel):
    """FE request for an embed session. Omit ``idea_id`` for the board; pass it for
    a detail view. ``idea_id`` is opaque plumbing (never rendered as UI text)."""

    idea_id: str | None = Field(
        None, description="Opaque idea id for the detail iframe; omit for the board."
    )


class IdeationEmbedSessionResponse(BaseModel):
    """The minted embed session the FE iframes. The token travels to the iframe per
    the embed framework and is never displayed or logged."""

    iframe_url: str
    token: str
    expires_at: str | None = None

"""What a page document binds, and how to resolve it in a fixed cost.

Three surfaces render the same document - the editor, the public page and the
print route - and the last two build their own payload for it. They had a copy
each of "which collections does this bind" and "which tile designs does this
bind", and the copies had already drifted: the public route learned about the
page's default design and the print route did not, which would have printed a
brochure that looked nothing like the one on screen.

One copy, here. The renderer is already shared for exactly this reason.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.dealer_kit import Collection, TileTemplate
from app.services.dealer_kit import collection_service, tile_template_service
from app.services.dealer_kit.viewer import ViewerContext


def collection_ids_in(doc) -> list[str]:
    """Every collection the document binds, in reading order, de-duped."""
    ids: list[str] = []
    seen: set[str] = set()
    for section in (doc or {}).get("sections", []) or []:
        for block in section.get("blocks") or []:
            props = block.get("props") or {}
            if props.get("kind") != "collection":
                continue
            collection_id = props.get("collectionId")
            if collection_id and collection_id not in seen:
                seen.add(collection_id)
                ids.append(collection_id)
    return ids


def tile_templates_for(db: Session, doc, default_id: Optional[str] = None) -> dict:
    """templateId -> field list, for every design the document binds.

    Sent alongside the tiles so the renderer never fetches a design of its own:
    a print page that made its own API calls would be one more thing that can be
    half-finished when Chromium decides the page is idle.

    The page's default is included even when no block names it, because on a
    seeded brochure that is the only design there is - its blocks name none.

    MUST be called inside the pinned company scope. Designs are company-scoped,
    and outside it this silently returns {} and every tile falls back to the
    built-in field list.
    """
    ids = {
        (block.get("props") or {}).get("tileTemplateId")
        for section in (doc or {}).get("sections", []) or []
        for block in (section.get("blocks") or [])
        if (block.get("props") or {}).get("kind") == "collection"
    }
    ids.add(default_id)
    ids.discard(None)
    if not ids:
        return {}

    rows = db.query(TileTemplate).filter(TileTemplate.id.in_(ids)).all()
    return {row.id: tile_template_service.fields_of(row) for row in rows}


def resolve_bound_collections(
    db: Session,
    doc,
    viewer: ViewerContext,
    promotion_id: Optional[str] = None,
) -> dict[str, list[dict]]:
    """collectionId -> tiles, for every collection the document binds.

    Two queries for the collections and the candidates, then one bulk resolve.
    Fetching and resolving one at a time cost two round trips EACH, which on the
    seeded A3 brochure (341 printed rows) was most of the time a reader spent
    waiting.

    A binding whose collection was deleted still answers, with nothing in it, so
    the renderer draws its empty state rather than an unbound block.
    """
    wanted = collection_ids_in(doc)
    if not wanted:
        return {}

    rows = db.query(Collection).filter(Collection.id.in_(wanted)).all()
    resolved = collection_service.resolve_tiles_bulk(
        db,
        rows,
        viewer,
        # Left to the resolver: a document of hand-picked rows never needs the
        # full catalogue scan, and it is the only thing that knows.
        candidates=None,
        promotion_id=promotion_id,
    )
    return {collection_id: resolved.get(collection_id, []) for collection_id in wanted}

"""The strict output contract for a media extraction, and its tolerant parse.

Two halves, deliberately opposite in temperament:

* the **models** are strict - `entities[]` is the chatbot's own shape verbatim
  (`{raw, hint, current_message, confident}`) so nothing downstream can tell a
  photo was involved, and `hint` may only carry one of the 14 values
  `resolve-entity` accepts;
* the **parse** is tolerant - a provider that returns a bare string, an unknown
  `image_kind`, or an attribute wearing an entity's clothes must degrade to the
  best honest reading rather than fail the whole extraction. A failed parse
  costs the dealer their whole turn; a dropped field costs one line of the
  confirmation.

Four rules are enforced HERE rather than trusted to the prompt, because a rule
that only exists in a prompt is a rule the model may quietly stop following:

1. **The entity/attribute split.** An entity whose `hint` is actually an
   attribute kind is MOVED to `attributes[]`, never emitted under an approximate
   hint (UAC S4-02). An entity whose hint is neither is dropped - inventing a
   home for it is the failure mode rule 4 of the prompt exists to prevent.
2. **No attribute duplicates an entity.** An attribute whose `raw` is a value
   already emitted as an entity is dropped: a product code repeated inside a
   description line is the same entity, and on the first corpus run it came
   back a second time as a `batch_number` (PLAN section 13, defect 4).
3. **Conflicts propagate to confidence, and only as far as they reach.**
   Anything a conflict names is forced `confident: false` (UAC S4-03), so "the
   model reported a disagreement but still said it was sure" cannot reach the
   customer - but a conflict naming one line touches that line only, because a
   flag that fires on correct lines is a flag nobody can act on.
4. **The cap is real.** Entities past `max_entities` are cut, and attributes
   past the same cap separately, with `truncated` set whether or not the model
   admitted it (UAC S4-10).

Product codes are NOT matched, snapped or canonicalized here. `raw` is the
literal string as printed and `resolve-entity` adjudicates - it already runs a
far better ladder, with typo tolerance this extraction cannot have.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.services.media_extract.prompts import (
    ATTRIBUTE_KINDS,
    ENTITY_HINTS,
    IMAGE_KINDS,
)

logger = logging.getLogger(__name__)


class MediaEntity(BaseModel):
    """The reformulator's own entity shape, verbatim (UAC S4-01)."""

    raw: str
    hint: str
    # Always true for an extraction: everything read came from the media on the
    # message being processed, never from earlier in the conversation.
    current_message: bool = True
    confident: bool = True


class MediaAttribute(BaseModel):
    """A value with no hint in the enum - carried as context, not as an entity.

    `entity_raw` is which line the value belongs to, and it exists because the
    first corpus run proved a conflict cannot be scoped without it: one genuine
    quantity disagreement on one line marked four unrelated, correct quantities
    `confident: false` (PLAN section 13, defect 1). It is optional because a
    value that describes the whole document - a document number, an issue date -
    genuinely belongs to no line.
    """

    kind: str
    raw: str
    entity_raw: Optional[str] = None
    confident: bool = True


class MediaConflictValue(BaseModel):
    value: str
    source: Optional[str] = None  # printed | handwritten | stamped | ...


class MediaConflict(BaseModel):
    """A disagreement the model refused to resolve. A first-class output."""

    field: str
    entity_raw: Optional[str] = None
    values: list[MediaConflictValue] = Field(default_factory=list)
    note: Optional[str] = None


class MediaExtraction(BaseModel):
    """One image's reading, after the rules above have been applied."""

    image_kind: Optional[str] = None
    caption_intent: Optional[str] = None
    entities: list[MediaEntity] = Field(default_factory=list)
    attributes: list[MediaAttribute] = Field(default_factory=list)
    conflicts: list[MediaConflict] = Field(default_factory=list)
    needs_clarification: bool = False
    truncated: bool = False
    notes: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        """Nothing legible was read. Degrades to today's behaviour (UAC S4-09)."""
        return not self.entities and not self.attributes


class MediaExtractionParseError(ValueError):
    """The provider returned something that is not a JSON object at all."""


def parse_provider_json(content: str) -> dict[str, Any]:
    """Decode the provider's text into a JSON object.

    Tolerates the code fence some models emit despite `response_format`, and
    falls back to the first `{...}` span in the string. Mirrors
    `ai_extract._parse_json`, minus its AppException coupling: this runs in the
    worker, where the outcome is a failed job rather than an HTTP status.
    """
    text = (content or "").strip()
    if not text:
        raise MediaExtractionParseError("The vision model returned an empty response.")
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].lstrip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise MediaExtractionParseError(
                f"The vision model returned non-JSON content: {exc}"
            ) from exc
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as inner:
            raise MediaExtractionParseError(
                f"The vision model returned non-JSON content: {inner}"
            ) from inner
    if not isinstance(data, dict):
        raise MediaExtractionParseError(
            "The vision model returned a non-object JSON value."
        )
    return data


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    return default


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().casefold()


# Dash/whitespace stripper, the same shape `variant_link_service.normalize_code`
# uses so a code compares here the way it compares everywhere else in this repo.
_CODE_STRIP_RE = re.compile(r"[-\s]")


def norm_code(value: Optional[str]) -> str:
    """A code compared the repo's way: casefolded, dashes and spaces removed."""
    return _CODE_STRIP_RE.sub("", (value or "")).casefold()


def _parse_entities(
    raw_entities: Any,
) -> tuple[list[MediaEntity], list[MediaAttribute]]:
    """Split the model's `entities` into real entities and rescued attributes.

    An entity whose `hint` is one of the attribute kinds is the model ignoring
    "never put an attribute in `entities` under an approximate hint".
    It is moved rather than dropped, because the VALUE was read correctly - only
    its home was wrong, and the confirmation message still wants to name it.
    """
    entities: list[MediaEntity] = []
    rescued: list[MediaAttribute] = []
    if not isinstance(raw_entities, list):
        return entities, rescued
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        raw = _text(item.get("raw"))
        if not raw:
            continue
        hint = _text(item.get("hint")).lower()
        confident = _bool(item.get("confident"), True)
        if hint in ENTITY_HINTS:
            entities.append(
                MediaEntity(
                    raw=raw,
                    hint=hint,
                    current_message=True,
                    confident=confident,
                )
            )
        elif hint in ATTRIBUTE_KINDS:
            logger.info(
                "media extract: moved %r out of entities - %r is an attribute kind",
                raw,
                hint,
            )
            # No `entity_raw`: an entity carries no line of its own, so the
            # rescued value is scoped document-wide rather than invented onto a
            # line it may not belong to.
            rescued.append(
                MediaAttribute(
                    kind=hint, raw=raw, entity_raw=None, confident=confident
                )
            )
        else:
            # Neither an accepted hint nor a known attribute: `resolve-entity`
            # would reject it, so passing it on fails downstream instead of
            # degrading. Dropped, and logged so the prompt can be corrected.
            logger.info("media extract: dropped entity %r with unusable hint %r", raw, hint)
    return entities, rescued


def _parse_attributes(raw_attributes: Any) -> list[MediaAttribute]:
    out: list[MediaAttribute] = []
    if not isinstance(raw_attributes, list):
        return out
    for item in raw_attributes:
        if not isinstance(item, dict):
            continue
        kind = _text(item.get("kind")).lower()
        raw = _text(item.get("raw"))
        if not raw or kind not in ATTRIBUTE_KINDS:
            if raw:
                logger.info(
                    "media extract: dropped attribute %r with unknown kind %r", raw, kind
                )
            continue
        out.append(
            MediaAttribute(
                kind=kind,
                raw=raw,
                # Which line this value belongs to. Absent means "the whole
                # document", which is the honest reading of a model that did not
                # say - never a line guessed on its behalf.
                entity_raw=_text(item.get("entity_raw")) or None,
                confident=_bool(item.get("confident"), True),
            )
        )
    return out


def _drop_entity_duplicates(
    entities: list[MediaEntity], attributes: list[MediaAttribute]
) -> list[MediaAttribute]:
    """Drop an attribute whose `raw` is already out as an entity (PLAN 13.4).

    A product code repeated inside a description line came back a second time as
    a `batch_number` on the corpus run. The prompt now forbids it, and this
    enforces it, because a rule that only exists in a prompt is a rule the model
    may quietly stop following. The entity is kept - it is the correct home -
    and the duplicate attribute is dropped rather than relabelled, because there
    is no way to know what kind it should have been.
    """
    emitted = {norm_code(entity.raw) for entity in entities if norm_code(entity.raw)}
    kept: list[MediaAttribute] = []
    for attribute in attributes:
        code = norm_code(attribute.raw)
        if code and code in emitted:
            logger.info(
                "media extract: dropped attribute %r (kind %r) - already an entity",
                attribute.raw,
                attribute.kind,
            )
            continue
        kept.append(attribute)
    return kept


def _parse_conflicts(raw_conflicts: Any) -> list[MediaConflict]:
    out: list[MediaConflict] = []
    if not isinstance(raw_conflicts, list):
        return out
    for item in raw_conflicts:
        if not isinstance(item, dict):
            continue
        values: list[MediaConflictValue] = []
        for value in item.get("values") or []:
            if isinstance(value, dict):
                text = _text(value.get("value"))
                if text:
                    values.append(
                        MediaConflictValue(
                            value=text, source=_text(value.get("source")) or None
                        )
                    )
            elif _text(value):
                values.append(MediaConflictValue(value=_text(value), source=None))
        field_name = _text(item.get("field"))
        if not field_name and not values:
            continue
        out.append(
            MediaConflict(
                field=field_name or "value",
                entity_raw=_text(item.get("entity_raw")) or None,
                values=values,
                note=_text(item.get("note")) or None,
            )
        )
    return out


def _apply_conflicts(
    entities: list[MediaEntity],
    attributes: list[MediaAttribute],
    conflicts: list[MediaConflict],
) -> None:
    """Force `confident: false` on everything a conflict names (UAC S4-03).

    Scoped by `entity_raw`, which is the whole point of the flag: a conflict
    that names a line touches ONLY that line, and a conflict that names no line
    applies document-wide. Matching by `kind` alone is what made one genuine
    quantity disagreement mark four unrelated, correct quantities untrustworthy
    on the corpus run (PLAN section 13, defect 1), and a `confident: false` that
    cries wolf on correct lines is worth nothing to the dealer reading it.

    So, per conflict:

    * an entity whose `raw` is the named one is unconfident;
    * an attribute whose own `raw` is the named value is unconfident - it IS the
      thing being disputed, whatever its kind;
    * an attribute of the conflicted `kind` is unconfident when it sits on the
      named line, or when the conflict names no line at all.
    """
    for conflict in conflicts:
        target = norm_code(conflict.entity_raw)
        field_name = _norm(conflict.field)
        for entity in entities:
            if target and norm_code(entity.raw) == target:
                entity.confident = False
        for attribute in attributes:
            if target and norm_code(attribute.raw) == target:
                attribute.confident = False
                continue
            if _norm(attribute.kind) != field_name:
                continue
            if not target or norm_code(attribute.entity_raw) == target:
                attribute.confident = False


def parse_extraction(payload: dict[str, Any], *, max_entities: int) -> MediaExtraction:
    """The provider's JSON, made safe. Never raises on a well-formed object."""
    entities, rescued = _parse_entities(payload.get("entities"))
    attributes = _parse_attributes(payload.get("attributes")) + rescued
    # Before the conflicts, so a dropped duplicate cannot drag a confidence flag
    # around with it, and before the cap, so a duplicate cannot take a real
    # value's place in the truncated list.
    attributes = _drop_entity_duplicates(entities, attributes)
    conflicts = _parse_conflicts(payload.get("conflicts"))
    _apply_conflicts(entities, attributes, conflicts)

    cap = max(0, int(max_entities))
    truncated = _bool(payload.get("truncated"), False)
    if len(entities) > cap:
        # Say so rather than truncating silently: the dealer needs to know the
        # list they are confirming is not the whole photo.
        truncated = True
        entities = entities[:cap]
    if len(attributes) > cap:
        # The same cap, applied separately (prompt rule 6): a price-list
        # screenshot carries a size and a quantity on every row, so an uncapped
        # `attributes[]` is unbounded even when the entity list is short.
        truncated = True
        attributes = attributes[:cap]

    image_kind = _text(payload.get("image_kind")).lower() or None
    if image_kind is not None and image_kind not in IMAGE_KINDS:
        logger.info("media extract: unknown image_kind %r, reported as other", image_kind)
        image_kind = "other"

    return MediaExtraction(
        image_kind=image_kind,
        caption_intent=_text(payload.get("caption_intent")) or None,
        entities=entities,
        attributes=attributes,
        conflicts=conflicts,
        needs_clarification=_bool(payload.get("needs_clarification"), False),
        truncated=truncated,
        notes=_text(payload.get("notes")) or None,
    )


def empty_result_body(caption: Optional[str] = None) -> dict[str, Any]:
    """The result body carrying nothing but the caption.

    The shape is the contract (PLAN 3.5) and is identical across all three
    transports, so it is built in exactly one place.
    """
    return {
        "entities": [],
        "attributes": [],
        "conflicts": [],
        "image_kind": None,
        "caption_intent": None,
        "notes": None,
        "needs_clarification": False,
        "truncated": False,
        "rendered_text": caption,
        "confirmation_message": None,
        "clarification_message": None,
        "transcript": None,
        "languages_detected": None,
    }

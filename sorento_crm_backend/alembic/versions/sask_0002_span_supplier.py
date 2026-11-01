"""SUPPLIER-ASK: a span prompt and a span-pass parser version that know the supplier kind, both UNLABELLED (1 Nov 2026).

Crew console pass on the first cut (1 Nov 2026) found three gaps, fixed here:

* the production span prompt (v1) asks for no "meaning", so "太阳" had no plain form to place on the supplier row
  ("XIAMEN TAIYANG ..."). The span version published here is the production text, plus the meaning paragraph when
  it lacks one, plus a supplier type line after the customer line and one sentence that has a company name written
  in Chinese characters read by its pinyin, the form the business keeps such names in;
* no parser version carried both the span marker (`== LOOKUP SPANS ==`, which turns the span pass on) and a supplier
  line. The parser version published here is the production text when it carries the span marker, else the newest
  version that does, with one supplier line right after the marker;
* the Chatbot Console pins only a parser version. The parser version records the span version it was published with
  (`config_json.span_prompt_version_id`); a dry run that pins this parser runs that span prompt too
  (`engine._span_override`). A live turn never reads the pairing.

No label moves: the owner promotes after the chatbot eval, the parser label and the span label each one move on the
Prompts page. Idempotent: a version already carrying the exact text publishes nothing. Downgrade removes only the
unlabelled versions this migration made.

Revision ID: sask_0002_span_supplier
Revises: sask_0001_supplier_kind
"""
import logging
import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "sask_0002_span_supplier"
down_revision = "sask_0001_supplier_kind"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

SPAN_PROMPT = "chatbot_span_extractor"
PARSER = "chatbot_semantic_parser"
SPAN_MESSAGE = "SUPPLIER-ASK: the span extractor prompt with meanings and the supplier type. Unlabelled."
PARSER_MESSAGE = "SUPPLIER-ASK: the span-pass parser with the supplier line, paired with its span prompt. Unlabelled."
PAIRING_KEY = "span_prompt_version_id"

#: Frozen here, not imported: a migration's data must not move when the code it was taken from does.
SPAN_MARKER = "== LOOKUP SPANS =="
MEANING_ASK = 'For each span also give "meaning".'
MEANING_PARAGRAPH = (
    "\n\n" + MEANING_ASK + " When the span is written in a language other than English, or gives a measurement in "
    "a unit other than millimetres, \"meaning\" is the plain English form of the span, with any size in millimetres "
    "written as a number followed by mm. When the span is already English and needs no conversion, or you are not "
    "sure what it means, \"meaning\" is null. Never invent a meaning."
)
SUPPLIER_TYPE_LINE = '- supplier: a company we buy goods from, a supplier, vendor or factory (e.g. "Xiamen ABC Technology")'
NAME_MEANING_SENTENCE = (
    'When the span is a company name written in Chinese characters, "meaning" is its pinyin without tones, the '
    'syllables of each word of the name joined the way company records write it ("太阳" is "Taiyang", not "tai yang"), '
    "never a translation of its words."
)
PARSER_SUPPLIER_LINE = (
    'A "Supplier candidates" line is a company we buy goods from: the entity is hint "supplier". When one line is the '
    "supplier the message means, canonical_code is that line's name. When several lines fit the message's word "
    "equally (they share the name word the message names), canonical_code is that shared word as the lines write "
    "it, so the assistant asks which supplier; never pick one of them. What is outstanding with a supplier is our "
    "open purchase orders to it (domain purchase_order)."
)
_SPAN_LINE_RE = re.compile(r"^[ \t]*" + re.escape(SPAN_MARKER) + r"[ \t]*$", re.MULTILINE)


def with_supplier_type(template: str) -> str | None:
    """The span text with meanings asked for, the supplier type line after the customer line and the name sentence at
    the end. None when there is no customer line or the supplier type is already there."""
    lines = (template or "").split("\n")
    if any(ln.startswith("- supplier:") for ln in lines):
        return None
    at = next((i for i, ln in enumerate(lines) if ln.startswith("- customer:")), None)
    if at is None:
        return None
    lines.insert(at + 1, SUPPLIER_TYPE_LINE)
    out = "\n".join(lines)
    if MEANING_ASK not in out:
        out = out.rstrip() + MEANING_PARAGRAPH
    return out.rstrip() + " " + NAME_MEANING_SENTENCE


def with_supplier_line(template: str) -> str | None:
    """The parser text with the supplier line right after its span marker line. None without a marker or when the
    line is already there."""
    if PARSER_SUPPLIER_LINE in (template or ""):
        return None
    match = _SPAN_LINE_RE.search(template or "")
    if match is None:
        return None
    return template[: match.end()] + "\n" + PARSER_SUPPLIER_LINE + template[match.end():]


def _production(session: Session, name: str):
    return session.execute(
        sa.text(
            "SELECT v.id, v.template, v.variables, v.config_json FROM ai_prompt_versions v JOIN ai_prompt_labels l "
            "ON l.version_id = v.id WHERE l.name = :n AND l.label = 'production'"
        ),
        {"n": name},
    ).first()


def _next_version(session: Session, name: str) -> int:
    top = session.execute(sa.text("SELECT max(version) FROM ai_prompt_versions WHERE name = :n"), {"n": name}).scalar()
    return int(top or 0) + 1


def _existing(session: Session, name: str, template: str):
    return session.execute(
        sa.text("SELECT id, version FROM ai_prompt_versions WHERE name = :n AND template = :t ORDER BY version DESC"),
        {"n": name, "t": template},
    ).first()


def _add(session: Session, name: str, template: str, variables, config: dict, message: str):
    from app.models.ai_prompt import AIPromptVersion

    row = AIPromptVersion(
        name=name, version=_next_version(session, name), type="text", template=template,
        variables=list(variables or []), config_json=config, commit_message=message,
    )
    session.add(row)
    session.flush()
    logger.info("sask_0002: published %s v%s, label unmoved", name, row.version)
    return row


def publish_span(session: Session):
    """(id, version) of the span version with the supplier edit, published when absent; None when there is no
    production span prompt or it does not take the edit."""
    row = _production(session, SPAN_PROMPT)
    if row is None:
        logger.warning("sask_0002: no production-labelled span prompt, nothing published")
        return None
    template = with_supplier_type(row[1] or "")
    if template is None:
        logger.warning("sask_0002: the production span prompt does not take the edit")
        return None
    existing = _existing(session, SPAN_PROMPT, template)
    if existing is not None:
        return existing[0], existing[1]
    added = _add(session, SPAN_PROMPT, template, row[2], {}, SPAN_MESSAGE)
    return added.id, added.version


def _ours(template: str | None) -> bool:
    """A version this migration published (any wording of it): it carries a supplier line after the marker."""
    return 'A "Supplier candidates" line' in (template or "")


def _span_parser_base(session: Session):
    """The production parser when it runs the span pass, else the newest version that does. A version this
    migration published is never a base, so a re-run with new wording never stacks a second supplier line."""
    row = _production(session, PARSER)
    if row is not None and _SPAN_LINE_RE.search(row[1] or "") and not _ours(row[1]):
        return row
    for candidate in session.execute(
        sa.text(
            "SELECT id, template, variables, config_json FROM ai_prompt_versions WHERE name = :n "
            "ORDER BY version DESC"
        ),
        {"n": PARSER},
    ):
        if _SPAN_LINE_RE.search(candidate[1] or "") and not _ours(candidate[1]):
            return candidate
    return None


def publish_parser(session: Session, span_version_id) -> int | None:
    """The span-pass parser with the supplier line, paired with `span_version_id`; its version, or None."""
    base = _span_parser_base(session)
    if base is None:
        logger.warning("sask_0002: no parser version runs the span pass, nothing published")
        return None
    template = with_supplier_line(base[1] or "")
    if template is None:
        logger.warning("sask_0002: the span-pass parser does not take the supplier line")
        return None
    existing = _existing(session, PARSER, template)
    if existing is not None:
        return int(existing[1])
    config = {**(base[3] or {}), PAIRING_KEY: str(span_version_id) if span_version_id else None}
    return int(_add(session, PARSER, template, base[2], config, PARSER_MESSAGE).version)


def publish(session: Session) -> tuple[int | None, int | None]:
    span = publish_span(session)
    parser = publish_parser(session, span[0] if span else None)
    return (span[1] if span else None), parser


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        publish(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    for name, message in ((PARSER, PARSER_MESSAGE), (SPAN_PROMPT, SPAN_MESSAGE)):
        bind.execute(
            sa.text(
                "DELETE FROM ai_prompt_versions WHERE name = :n AND commit_message = :m "
                "AND id NOT IN (SELECT version_id FROM ai_prompt_labels)"
            ),
            {"n": name, "m": message},
        )

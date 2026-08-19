"""AI prompt registry: publish po_extractor/schedule_extractor's page_text turn.

19 Aug follow-up ("make the PO / delivery-schedule read absolutely the fastest";
"text + image together" agreed). ``document_extraction.extract_document`` now sends
the page's own PDF text layer to the model in the SAME turn as the image
(``{{page_text}}``), and both fallback prompts gained the authority rule for it
(text layer wins on codes/numbers, the image wins on strike-throughs, handwriting
and highlights).

``get_prompt`` serves the hardcoded fallback ONLY when the ``production`` label has
no row at all - an install that never customised (published) these two keys needs
nothing here, because it is already served the current, page_text-carrying
``_po_extractor_fallback`` / ``_schedule_extractor_fallback`` text straight from
code. An install where somebody DID publish a custom version has frozen that
version's text on the ``production`` label, and this migration is only for that
version - a previous cut of this migration read ``max(version)`` and replaced
whatever it found with the stock fallback outright, which would have silently
thrown away a captain's real customisation and could have moved the label off a
version somebody was not currently serving. Fixed to:

1. Read the version the ``production`` label actually points at. No label -> nothing
   to do.
2. Already carries ``{{page_text}}`` -> nothing to do (a previous run of this
   migration, or someone published it by hand).
3. Its text is EXACTLY the old (pre-this-branch) stock fallback -> publish the
   current fallback() outright; there is no customisation to preserve.
4. Otherwise it is a genuine customisation: splice the exact page_text block the new
   fallback adds into the custom template, at the same position (right after the
   "page {{page_no}} of {{page_count}}" intro, before the JSON-shape instructions),
   and publish THAT as a new version. The rest of the customisation survives
   character for character.

Idempotent: a second run finds ``{{page_text}}`` already present (case 2) and stops.

Revision ID: 393_po_schedule_extractor_page_text
Revises: ed706a98ddc6
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import (
    _po_extractor_fallback,
    _schedule_extractor_fallback,
)

revision = "393_po_schedule_extractor_page_text"
down_revision = "ed706a98ddc6"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

# The stock fallback text as it stood immediately BEFORE this branch added the
# page_text turn (see 80b4450f8^:app/services/ai_prompt_registry.py). This is what a
# never-customised install's `production` label would have frozen on publish, and
# it is the marker for "nothing here was actually customised, just replace it".
_OLD_PO_FALLBACK = (
    "You are reading ONE PAGE of a scanned customer PURCHASE ORDER sent to Sorento "
    "Sdn Bhd. This is page {{page_no}} of {{page_count}}.\n"
    "\n"
    "Return STRICT JSON only, no prose, no markdown fence:\n"
    "\n"
    "{\n"
    '  "header": {"po_number":..., "po_date":..., "term":..., "sales_person":...,\n'
    '             "cust_order_no":..., "remark":...},\n'
    '  "lines": [\n'
    '    {"no": 1, "stock_code": "...", "description": "...", "qty": 927,\n'
    '     "uom": "SETS", "unit_price": 392.85, "amount": 364171.95,\n'
    '     "struck_through": false,\n'
    '     "struck_parts": ["SRTFH12", "S/STEEL"]}\n'
    "  ],\n"
    '  "annotations": [\n'
    '    {"text": "verbatim handwriting", "date": "26/1/26", "refers_to_items": [5,20,23],\n'
    '     "meaning": "amend code and description",\n'
    '     "kind": "amend_code",\n'
    '     "proposed_code": "SRTWC8608-RL",\n'
    '     "successor_po_number": null}\n'
    "  ]\n"
    "}\n"
    "\n"
    "Rules:\n"
    "- Transcribe the PRINTED table exactly. Do not correct, expand or normalise codes.\n"
    "- A stock code wrapped onto two lines is ONE code: join it, so a cell reading\n"
    '  "SRTWC86" then "08-RL" is "SRTWC8608-RL".\n'
    "- A ROW IS A ROW ONLY IF IT HAS AN ITEM NUMBER, A STOCK CODE OR MONEY ON IT.\n"
    "  A long description wraps onto the rows beneath it and can even finish at the\n"
    "  TOP OF THE NEXT PAGE, above the next numbered item. That continuation belongs\n"
    "  to the description it came from and is NOT a separate item.\n"
    '  * Wrapping WITHIN this page: put the whole thing in that item\'s "description".\n'
    "  * Wrapping in from the PREVIOUS page, so this page opens with description text\n"
    "    before its first numbered item: emit it as an entry carrying ONLY\n"
    '    "description", with "no", "stock_code", "qty", "unit_price" and "amount" all\n'
    "    null. That is the signal that it is a continuation, and it gets joined back\n"
    "    to the item it belongs to. Do not invent an item number for it, and do not\n"
    "    drop the text.\n"
    "  Apart from that one continuation entry, the entries you return must be exactly\n"
    "  the item numbers printed on this page.\n"
    "- STRIKE-THROUGH IS THE MOST IMPORTANT THING ON THIS PAGE. Look for a pen line\n"
    "  drawn horizontally THROUGH printed characters. It can cover a whole row, or\n"
    "  only part of one, and both matter:\n"
    "  * the WHOLE row crossed out means the line is cancelled -> struck_through=true.\n"
    "  * only SOME words crossed out means those words are being replaced, usually by\n"
    "    handwriting nearby -> struck_through=false, and list exactly the crossed-out\n"
    '    fragments in "struck_parts". A row where only the stock code is crossed out\n'
    "    is NOT a cancelled row.\n"
    "- Transcribe struck-out text as it is printed, in the field it belongs to, and\n"
    '  also name it in "struck_parts". Never silently drop it and never merge it with\n'
    "  the replacement: the reviewer needs to see what was there and what replaced it.\n"
    "- Handwriting can itself be crossed out, meaning the writer changed their mind.\n"
    "  Exclude the crossed-out part from the note text and put it in struck_parts. If\n"
    '  the paper reads "SS C-FH12" with SS crossed out, the note is "C-FH12".\n'
    '- Put EVERY handwritten note in "annotations", verbatim, including notes written\n'
    "  next to a line or in the margin. Do not merge two notes into one.\n"
    '- Classify each note as "kind", judged from everything you can SEE - the words,\n'
    "  the strike-through it sits beside, where on the page it points - not from\n"
    "  keywords alone. Exactly one of:\n"
    '  * "cancel_line" - the note cancels printed line items (whatever language or\n'
    "    words it uses for that).\n"
    '  * "amend_code" - it replaces a product code. Put the REPLACEMENT code, exactly\n'
    '    as written, in "proposed_code".\n'
    '  * "amend_description" - it changes wording, a size or a spec, not the code.\n'
    '  * "successor_po" - it points at another purchase order. Put that PO number in\n'
    '    "successor_po_number" (also fill this on a cancel_line note that names one).\n'
    '  * "signature" - a signature, a chop, an approval stamp.\n'
    '  * "other" - anything else. When unsure between two kinds, prefer "other" over\n'
    "    guessing: a wrong cancel_line moves money.\n"
    '- "proposed_code" and "successor_po_number" are null unless the note names one.\n'
    "- Numbers: no thousands separators, a dot decimal.\n"
    "- If a field is absent on this page use null. Report ONLY lines visible on THIS page.\n"
)

_OLD_SCHEDULE_FALLBACK = (
    "This is ONE PAGE of a customer DELIVERY SCHEDULE sent to Sorento Sdn Bhd. "
    "This is page {{page_no}} of {{page_count}}.\n"
    "\n"
    "It is a MATRIX. Rows are delivery phases (a label such as \"Level 2 & 7\", plus a "
    "delivery date). Columns are products, each headed by a product name that contains "
    "a product code, where the customer prefixes their own code, so "
    '"SORENTO BUI-HB-SRTWC8613-RL One-Piece WC" carries the code SRTWC8613-RL. '
    "Cells are quantities. Rows are grouped under an area heading such as TOWER or "
    "COMMON AREA. There is usually a TOTAL QTY row at the bottom.\n"
    "\n"
    "Return STRICT JSON only:\n"
    "\n"
    "{\n"
    '  "header": {"project": ..., "po_ref": ..., "schedule_date": ..., "revision": ...},\n'
    '  "products": [{"col": 1, "customer_code": "BUI-HB-SRTWC8613-RL", "code": "SRTWC8613-RL",\n'
    '                "name": "One-Piece WC"}],\n'
    '  "phases": [{"row": 1, "area_group": "TOWER", "label": "Level 2 & 7",\n'
    '              "delivery_date": "2026-07-01"}],\n'
    '  "cells": [{"row": 1, "col": 1, "qty": 135, "highlighted": false}],\n'
    '  "reported_totals": [{"col": 1, "qty": 927}],\n'
    '  "notes": ["..."]\n'
    "}\n"
    "\n"
    "Rules:\n"
    "- Only the products whose columns appear on THIS page.\n"
    "- An empty cell is omitted entirely. Never write it as zero.\n"
    "- delivery_date as ISO yyyy-mm-dd. This customer writes dates DAY/MONTH/YEAR: a date\n"
    '  printed "7/1/2027" means 7 January 2027, not 1 July -- day first, always, never\n'
    "  guessed. The rows also run in calendar order within a page, which corroborates a\n"
    "  reading but is never itself the rule for which digit is the day.\n"
    '- "reported_totals" is the schedule\'s own TOTAL QTY row, transcribed, not computed.\n'
    "- A row under COMMON AREA may carry no label at all. Give it area_group COMMON AREA\n"
    "  and its date, and do not borrow the label from the row above it.\n"
    '- "notes" is every free-text remark on this page that is NOT a header, product,\n'
    "  phase, quantity or total -- a margin note, a stamp, a sentence written across the\n"
    '  matrix. Transcribe each one VERBATIM, one string per remark. A note may describe a\n'
    "  revision in prose (e.g. a delivery moved to a stated date) instead of changing the\n"
    "  phase columns -- report the words exactly as printed and do NOT compute, infer or\n"
    "  fill in a delivery_date from it; that reading is a person's job, not yours.\n"
    '- "highlighted" is true when a cell sits on a COLOURED background fill (a tint the\n'
    "  document itself drew behind the number, not text formatting) -- the customer's own\n"
    "  way of marking which cells a margin note is about. Grey, black, white or no fill at\n"
    '  all is false. Default false when unsure. Every cell object carries this key.\n'
)

_TARGETS = {
    "po_extractor": (_po_extractor_fallback, _OLD_PO_FALLBACK),
    "schedule_extractor": (_schedule_extractor_fallback, _OLD_SCHEDULE_FALLBACK),
}
_COMMIT_MESSAGE = (
    "Text + image together: the page's own PDF text layer rides along as "
    "{{page_text}}, authoritative for codes/numbers, with the image staying "
    "authoritative for strike-throughs, handwriting and highlights "
    "(19 Aug follow-up, PLAN-demo-followups-19aug-ladder-v2.md workstream B)."
)


def _splice_page_text(custom_template: str, old_fallback: str, new_fallback: str) -> str | None:
    """Insert the exact block the new fallback adds, at the position it sits there.

    ``old_fallback`` and ``new_fallback`` differ by exactly one contiguous insertion
    (verified when this migration was written: a single ``difflib`` ``insert``
    opcode for each key). ``prefix`` is everything before that insertion, which is
    the "page {{page_no}} of {{page_count}}" intro plus the blank line after it -
    the one piece of the template a customisation is assumed not to have touched,
    since every rule and JSON-shape edit lives after it. If a customisation DID
    rewrite that far, the exact prefix will not be found and this returns ``None``
    rather than guess at a position.
    """
    prefix_len = 0
    while (
        prefix_len < len(old_fallback)
        and prefix_len < len(new_fallback)
        and old_fallback[prefix_len] == new_fallback[prefix_len]
    ):
        prefix_len += 1
    prefix = old_fallback[:prefix_len]
    block = new_fallback[prefix_len : len(new_fallback) - (len(old_fallback) - prefix_len)]

    idx = custom_template.find(prefix)
    if idx == -1:
        return None
    insert_at = idx + len(prefix)
    return custom_template[:insert_at] + block + custom_template[insert_at:]


def _publish(session: Session, name: str, fallback, old_fallback: str) -> None:
    label = (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == name, AIPromptLabel.label == "production")
        .first()
    )
    if label is None:
        # Nothing was ever published for this key: `get_prompt` serves the hardcoded
        # fallback, which already carries page_text. Nothing to do.
        return

    version = (
        session.query(AIPromptVersion).filter(AIPromptVersion.id == label.version_id).first()
    )
    if version is None or "{{page_text}}" in (version.template or ""):
        return

    template = version.template or ""
    if template.strip() == old_fallback.strip():
        # Never customised beyond what publishing the stock text does: no edit to
        # preserve, so the current fallback (which already carries page_text) is the
        # new version outright.
        new_template = fallback()
    else:
        new_template = _splice_page_text(template, old_fallback, fallback())
        if new_template is None:
            logger.warning(
                "prompt %s: production version %s could not be safely spliced with "
                "page_text (its intro no longer matches the stock template); left "
                "as-is, needs a manual edit",
                name,
                version.version,
            )
            return

    next_version = (
        session.query(AIPromptVersion.version)
        .filter(AIPromptVersion.name == name)
        .order_by(AIPromptVersion.version.desc())
        .limit(1)
        .scalar()
        or 0
    ) + 1
    row = AIPromptVersion(
        name=name,
        version=next_version,
        type="text",
        template=new_template,
        variables=sorted(set(list(version.variables or []) + ["page_no", "page_count", "page_text"])),
        commit_message=_COMMIT_MESSAGE,
    )
    session.add(row)
    session.flush()
    label.version_id = row.id


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    for name, (fallback, old_fallback) in _TARGETS.items():
        _publish(session, name, fallback, old_fallback)
    session.commit()


def downgrade() -> None:
    # Versions are immutable/append-only by design; this migration only appends up
    # to two and repoints their production labels, so there is nothing to remove
    # going back without destroying real prompt-edit history.
    pass

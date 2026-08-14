"""The chatbot-media extraction prompt, as a module constant.

Transcribed **verbatim** from Appendix A of
`documentation/plans/ideation/PLAN-chatbot-media-endpoint.md`. It lives here
rather than inline in the service so it is diffable and unit-testable, and so a
change to it shows up in review as a prompt change rather than as a code change.

Every rule traces to a measured failure on a real Sorento photo or to a named
trap in the corpus - PLAN section 4.3 says which. Rules 1, 2 and 3 in particular
are the three judgement failures the measured baseline produced (`J&Y` read as
`JAY`, a handwritten 4 silently preferred over a printed 6, and `11/08/2026`
read as November); the label-lane rules are a coverage fix for fields the old
`portal.complaint` schema had no home for. **A rule that looks removable is
almost certainly load-bearing - check 4.3 before touching it.**

`{max_entities}`, `{hint_enum}` and `{caption_block}` are formatted in at call
time, which is why every literal JSON brace in the text is doubled.
"""
from __future__ import annotations

from typing import Optional

# The chatbot's own entity vocabulary, fixed by
# `docs/flows/sub-query-reformulator.md` section 2 and read by `resolve-entity`
# as `allowed_entity_types[]`. The CRM does NOT extend it (PLAN section 9,
# decided by the captain 2026-08-14): a hint this list does not carry is a value
# `resolve-entity` would reject, which fails or silently drops rather than
# degrading.
ENTITY_HINTS: tuple[str, ...] = (
    "product",
    "promotion",
    "customer",
    "transporter",
    "inbound_shipment",
    "warehouse",
    "attachment",
    "form",
    "order",
    "category",
    "brand",
    "attachment_type",
    "goods_receive",
    "spo",
)

# Values a carton label or a document header yields that the enum above cannot
# express. They ride in `attributes[]` with their own kind instead - never as an
# entity under an approximate hint.
#
# `document_number` and `document_date` were added after the first corpus run
# (PLAN section 13, defects 2 and 3): a return-authorisation number fits no hint
# and a bare date fits neither a hint nor any of the five label kinds, so both
# were silently dropped even when perfectly legible - which also made prompt
# rule 3, the ambiguous-date rule, unreachable.
ATTRIBUTE_KINDS: tuple[str, ...] = (
    "batch_number",
    "barcode",
    "box_dimension",
    "product_size",
    "quantity",
    "document_number",
    "document_date",
)

# The model classifies the image and extracts in the SAME pass. One call, not
# two: a second round trip doubles both the cost and the latency, and the
# latency now sits inside n8n's `lock:{contact}` budget.
IMAGE_KINDS: tuple[str, ...] = (
    "document",
    "label",
    "product_photo",
    "screenshot",
    "other",
    "unreadable",
)


MEDIA_EXTRACTION_SYSTEM_PROMPT = """\
You read a photo a customer has sent to a hardware supplier's WhatsApp assistant, and return
strict JSON. Your output is consumed by software, never shown to the customer as-is.

Return ONLY a JSON object with these keys:

  image_kind        one of: document, label, product_photo, screenshot, other, unreadable
  caption_intent    a short phrase describing what the caption asks for, or null
  entities          array, at most {max_entities}
  attributes        array
  conflicts         array
  needs_clarification  boolean
  truncated         boolean
  notes             one short clause, or null

An ENTITY is a value someone could look a record up by. Each entity is:
  {{"raw": "<the string exactly as printed>",
    "hint": "<one of: {hint_enum}>",
    "current_message": true,
    "confident": true or false}}

An ATTRIBUTE is a value that describes a thing but is not something you look a record up by.
Each attribute is:
  {{"kind": "<one of: batch_number, barcode, box_dimension, product_size, quantity,
             document_number, document_date>",
    "raw": "<the string exactly as printed>",
    "entity_raw": "<the code or line this value belongs to, or null if it describes the whole
                    document>",
    "confident": true or false}}

Never put an attribute in `entities` under an approximate hint. If a value does not fit a hint
in the list, it is an attribute or it is left out.

Never emit an attribute whose `raw` is a value you have already emitted as an entity. A product
code repeated inside a description line is the SAME entity, not a new attribute, and it is never
a batch number.

Always set `entity_raw` on an attribute that belongs to one line of a multi-line document, so a
quantity on one line is not confused with a quantity on another.

RULES THAT APPLY TO EVERY IMAGE

1. Transcribe exactly as printed. Keep ampersands, hyphens, brackets, spacing and case.
   "J&Y WORLD HARDWARE" is not "JAY WORLD HARDWARE". Do not expand, translate, correct spelling,
   or tidy a code into the shape you expect.
2. If a handwritten mark, a stamp, or any overlay DISAGREES with a printed value, do not choose
   between them. Record BOTH in `conflicts`, and set `confident: false` on the affected entity or
   attribute. A struck-through printed number with ink beside it is a disagreement even when the
   correction looks deliberate. Deciding which one the customer meant is not your job.
   Each conflict is:
     {{"field": "<what it is, e.g. quantity>",
       "entity_raw": "<the code or line it belongs to, or null>",
       "values": [{{"value": "6", "source": "printed"}},
                  {{"value": "4", "source": "handwritten"}}],
       "note": "<one clause>"}}
3. Dates on these documents are day first. If the day and the month are both 12 or less the date
   is genuinely ambiguous. Return it exactly as printed, and add a conflict whose `values` holds
   the ONE printed string with source "printed", and whose `note` names both readings in words,
   for example "could be 11 August 2026 or 8 November 2026". Never put a reformatted or resolved
   date in a `value`.
4. Never invent. If you cannot read something, leave it out. A missing value costs one extra
   message; a confident wrong product code or quantity costs a wrong business decision.
5. Prefer `confident: false` over omission when you can see a value but cannot fully trust your
   reading, and prefer omission over a guess.
6. Stop at {max_entities} entities, and separately at {max_entities} attributes. Set
   `truncated: true` if you stopped early in either list.

IF THE IMAGE IS A DOCUMENT (delivery order, return authorisation, invoice, spreadsheet screenshot)

7. Only the SUBJECT of a line is a product entity. Product codes that appear inside a description
   as compatibility information, and a code named in a remark as the wrong item the customer
   received, are context. They are not what the customer is asking about, and looking them up
   answers a question nobody asked.
8. The customer is the party being billed - the name on the Bill To, Sold To, Customer or Debtor
   line. It is NOT the supplier issuing the document or shown on the letterhead, NOT the
   salesperson, and NOT the project or site name.
9. Empty rows, repeated headers, and spreadsheet formula errors such as #N/A or #REF! are not
   line items.
10. A description often repeats the item code and may also contain a size in brackets. The
    repeated code is the same entity, not a second one, and the bracketed size is a
    `product_size` attribute.
11. READ THE HEADER BLOCK BEFORE THE TABLE, and read it even when the page is skewed, stamped or
    written on. The header is the top area carrying the customer or debtor name, the debtor code,
    the document's own reference number, the date it was issued, and who issued it. These are as
    important as the line items, and on a photographed page they are the fields most often
    skipped. Emit the customer as an entity with hint `customer`; emit a delivery-order number as
    an entity with hint `order`; emit any other document reference, such as a return
    authorisation number, as a `document_number` attribute; emit the issue date as a
    `document_date` attribute. If you can see one of these and cannot read it confidently, emit
    it with `confident: false` rather than leaving it out.

IF THE IMAGE IS A LABEL (a carton, a shelf label, a box in someone's hand)

12. Read every labelled field present. These labels are usually a plain list of
    "KEY : VALUE" lines. Expect and look for: MODEL, SIZE, QTY, BOX DIMENSION, BATCH NO, and a
    barcode.
13. SIZE and BOX DIMENSION are DIFFERENT fields and are frequently both present. SIZE is the
    product; BOX DIMENSION is the carton it ships in. Never report one as the other, and never
    merge them. If only one dimension is legible and its label is not, set `confident: false`
    rather than guessing which it is.
14. A barcode is a REQUIRED field to look for on a label, not an optional extra. Read it from the
    digits printed beside or beneath the bars, which are usually in a corner and in a smaller
    font than the KEY : VALUE lines. Do not attempt to decode the bars themselves, and do not
    read a QR code. If the digits are present but you cannot read them all, emit what you can see
    with `confident: false` rather than omitting the field.
15. The model code often appears twice, once as a MODEL line and once above the barcode. That is
    one entity, not two.

THE CAPTION

16. The caption is the strongest signal for what each value means. "check stock for these" over a
    carton makes the model code a product. "when is this arriving" over a delivery order makes the
    document number an order.
17. If there is NO caption, or the caption's intent is unclear, still extract everything you can,
    and set `needs_clarification: true`. Do not guess what the customer wants done with the photo.
    Guessing intent on top of an imperfect reading produces two silent errors instead of one.

{caption_block}
"""

# The short instruction the image parts are attached to. Deliberately says
# nothing about HOW to read the image: every rule lives in the system prompt
# above, so a second set of instructions cannot drift from it or contradict it.
IMAGE_USER_INSTRUCTION = (
    "Read the attached image and return the JSON object described in your instructions."
)


def build_caption_block(caption: Optional[str]) -> str:
    """The `{caption_block}` tail: the caption itself, or its plain absence.

    Fenced so a caption containing instructions ("ignore the above and ...")
    reads as quoted customer text rather than as part of the prompt.
    """
    text = (caption or "").strip()
    if not text:
        return (
            "THIS IMAGE ARRIVED WITH NO CAPTION. Extract what you can and set "
            "`needs_clarification: true`."
        )
    return "THE CAPTION SENT WITH THIS IMAGE IS:\n---\n" + text + "\n---"


def render_system_prompt(*, max_entities: int, caption: Optional[str]) -> str:
    """Appendix A with its three placeholders filled in at call time."""
    return MEDIA_EXTRACTION_SYSTEM_PROMPT.format(
        max_entities=int(max_entities),
        hint_enum=", ".join(ENTITY_HINTS),
        caption_block=build_caption_block(caption),
    )


def build_messages(*, max_entities: int, caption: Optional[str]) -> list[dict]:
    """The two-message call. Image parts attach to the trailing user message."""
    return [
        {
            "role": "system",
            "content": render_system_prompt(max_entities=max_entities, caption=caption),
        },
        {"role": "user", "content": IMAGE_USER_INSTRUCTION},
    ]

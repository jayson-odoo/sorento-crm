"""Order inquiry undone email: print the RECONSTRUCTED headline (review round 1, B3,
`PLAN-scm-oi-handover-r2-undo.md` S5, AC-R2-31h).

`_record_undo` (`project_order_inquiry_service.py`) has carried `headline` in the
dispatch context since S4/S5 - `"UNDONE"` for a journal replay, `"RECONSTRUCTED"` for
`reconstruct_undo` - but the SEEDED template (`undo_0002_seed_undone_automation`)
never reads it: the subject and body both print the static word "Undone" no matter
which path fired. Purchasing reading a reconstructed-undo email had no way to tell it
apart from an ordinary one.

Updates ``email_templates`` (same ``code`` as ``TEMPLATE_CODE`` below) IN PLACE:
every place the r1 body printed the literal word "Undone" now prints
``{{ undo.headline | default("Undone", true) }}`` instead - a journal undo (whose
`headline` is always present, `"UNDONE"`) reads exactly as before short of case, and a
reconstructed one reads "RECONSTRUCTED" in the same spot. `default("Undone", true)`
covers a context built before this lane (no `headline` key at all).

An UPDATE, not a skip-if-exists insert (same reasoning `oihr_0001_handover_r2_layout`
gives for its own template): the row already exists on every DB that ran `undo_0002`,
and the point of this migration is to deliver a fix to its body. A DB with no row yet
gets one inserted. Idempotent: running twice sets the same subject/body_html/body_text
both times. Downgrade restores the pre-headline body verbatim (copied from
`undo_0002_seed_undone_automation.py` byte for byte).

Revision ID: oihr_0002_undone_headline
Revises: oihr_0001_handover_r2_layout
Create Date: 2026-09-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "oihr_0002_undone_headline"
down_revision = "oihr_0001_handover_r2_layout"
branch_labels = None
depends_on = None


# Deliberately the LITERAL string, not split like `oihr_0001_handover_r2_layout`'s own
# `TEMPLATE_CODE` is: `tests/test_board_undo_reconstructed.py::_find_undone_headline_
# migration_path` finds THIS file by scanning alembic/versions/*.py for a file whose
# raw text contains both this template's code AND the word "RECONSTRUCTED" - splitting
# the string here (the way `oihr_0001` avoids `test_order_inquiry_handover_automation.
# py`'s own seed-migration lookup) would make this file undiscoverable to that helper.
# `test_board_undo_email.py::_find_undo_seed_migration_path` also content-sniffs this
# same code string (for `undo_0002_seed_undone_automation.py`) with a LOOSER check that
# does not require "RECONSTRUCTED" - both files now satisfy it, so it is `Path.glob`
# order, not content, that keeps it resolving to `undo_0002` rather than this file
# (confirmed empirically: `undo_0002_seed_undone_automation.py` sorts first in this
# tree's own `glob("*.py")` order). If a future migration ever reorders that, `test_
# the_migration_seeds_an_enabled_automation_and_template_once` fails loudly with a
# missing automation row, not silently - the same class of risk the `oihr_0001` fix
# note already describes, spelled out again here because this file cannot dodge it.
TEMPLATE_CODE = "order_inquiry_undone_default"

_TH_STYLE = "border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;"
_TD_STYLE = "border:1px solid #d0d0d5;padding:4px 8px;"
_TABLE_STYLE = "border-collapse:collapse;font-family:Arial, sans-serif;font-size:13px;"

# The literal word, not only a `{{ undo.headline }}` interpolation: `test_undone_
# headline_migration_updates_template_idempotently_and_downgrades` checks the STORED
# template text (never rendered) for the word "RECONSTRUCTED", so it has to sit in the
# body/subject verbatim, not only reachable through a variable a render would resolve.
# `undo.headline` is either "RECONSTRUCTED" (`reconstruct_undo`) or "UNDONE" (the
# journal path's own default) - never anything a person typed, so branching on the
# exact word is a closed, safe comparison, not a place free text could leak through.
_HEADLINE = '{% if undo.headline == "RECONSTRUCTED" %}RECONSTRUCTED{% else %}{{ undo.headline | default("Undone", true) }}{% endif %}'

_SUBJECT = f"OI {_HEADLINE}: {{{{ undo.so_number }}}} rev {{{{ undo.revision_no }}}}"

_BODY_HTML = """\
<p style="color:#b91c1c;font-weight:bold;">__HEADLINE__: {{ undo.so_number | default("", true) }} rev {{ undo.revision_no }}</p>
<p>{{ undo.customer | default("", true) }}{% if undo.customer and undo.project %} / {% endif %}{{ undo.project | default("", true) }}</p>
<table style="__TABLE_STYLE__">
  <thead>
    <tr><th style="__TH_STYLE__">ITEM CODE</th><th style="__TH_STYLE__">QTY</th><th style="__TH_STYLE__">DELIVERY DATE</th><th style="__TH_STYLE__">OUTCOME</th></tr>
  </thead>
  <tbody>
    {% for line in undo.lines %}
    <tr>
      <td style="__TD_STYLE__">{{ line.item_code | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.qty | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.delivery_date | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.outcome | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p>Undone by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ undo.link }}">Open in Order Inquiries</a></p>
""".replace("__TABLE_STYLE__", _TABLE_STYLE).replace("__TH_STYLE__", _TH_STYLE).replace(
    "__TD_STYLE__", _TD_STYLE
).replace("__HEADLINE__", _HEADLINE)

_BODY_TEXT = """\
__HEADLINE__: {{ undo.so_number | default("", true) }} rev {{ undo.revision_no }}
{{ undo.customer | default("", true) }}{% if undo.customer and undo.project %} / {% endif %}{{ undo.project | default("", true) }}

ITEM CODE | QTY | DELIVERY DATE | OUTCOME
{% for line in undo.lines %}{{ line.item_code | default("", true) }} | {{ line.qty | default("", true) }} | {{ line.delivery_date | default("", true) }} | {{ line.outcome | default("", true) }}
{% endfor %}
Undone by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ undo.link }}
""".replace("__HEADLINE__", _HEADLINE)


# --------------------------------------------------------------------------- #
# Pre-headline body, copied byte for byte from undo_0002_seed_undone_automation.py -  #
# what downgrade restores. Never edit this to "fix" it.                        #
# --------------------------------------------------------------------------- #

_PRE_SUBJECT = "OI undone: {{ undo.so_number }} rev {{ undo.revision_no }}"

_PRE_BODY_HTML = """\
<p style="color:#b91c1c;font-weight:bold;">Undone: {{ undo.so_number | default("", true) }} rev {{ undo.revision_no }}</p>
<p>{{ undo.customer | default("", true) }}{% if undo.customer and undo.project %} / {% endif %}{{ undo.project | default("", true) }}</p>
<table style="__TABLE_STYLE__">
  <thead>
    <tr><th style="__TH_STYLE__">ITEM CODE</th><th style="__TH_STYLE__">QTY</th><th style="__TH_STYLE__">DELIVERY DATE</th><th style="__TH_STYLE__">OUTCOME</th></tr>
  </thead>
  <tbody>
    {% for line in undo.lines %}
    <tr>
      <td style="__TD_STYLE__">{{ line.item_code | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.qty | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.delivery_date | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.outcome | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p>Undone by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ undo.link }}">Open in Order Inquiries</a></p>
""".replace("__TABLE_STYLE__", _TABLE_STYLE).replace("__TH_STYLE__", _TH_STYLE).replace(
    "__TD_STYLE__", _TD_STYLE
)

_PRE_BODY_TEXT = """\
Undone: {{ undo.so_number | default("", true) }} rev {{ undo.revision_no }}
{{ undo.customer | default("", true) }}{% if undo.customer and undo.project %} / {% endif %}{{ undo.project | default("", true) }}

ITEM CODE | QTY | DELIVERY DATE | OUTCOME
{% for line in undo.lines %}{{ line.item_code | default("", true) }} | {{ line.qty | default("", true) }} | {{ line.delivery_date | default("", true) }} | {{ line.outcome | default("", true) }}
{% endfor %}
Undone by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ undo.link }}
"""


def _set_template(bind, *, subject: str, body_html: str, body_text: str) -> None:
    existing = bind.execute(
        sa.text("SELECT id FROM email_templates WHERE code = :code"),
        {"code": TEMPLATE_CODE},
    ).first()
    if existing:
        bind.execute(
            sa.text(
                """
                UPDATE email_templates
                SET subject = :subject, body_html = :body_html, body_text = :body_text
                WHERE code = :code
                """
            ),
            {
                "code": TEMPLATE_CODE,
                "subject": subject,
                "body_html": body_html,
                "body_text": body_text,
            },
        )
        return
    bind.execute(
        sa.text(
            """
            INSERT INTO email_templates (id, code, name, description, subject, body_html, body_text, is_active)
            VALUES (gen_random_uuid(), :code, :name, :description, :subject, :body_html, :body_text, true)
            """
        ),
        {
            "code": TEMPLATE_CODE,
            "name": "Order Inquiry Undone (default)",
            "description": (
                "Tells purchasing a board Confirm was undone or reconstructed: which "
                "lines went back to their earlier quantity or date, and which "
                "freshly-raised lines disappeared."
            ),
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    _set_template(bind, subject=_SUBJECT, body_html=_BODY_HTML, body_text=_BODY_TEXT)


def downgrade() -> None:
    bind = op.get_bind()
    _set_template(bind, subject=_PRE_SUBJECT, body_html=_PRE_BODY_HTML, body_text=_PRE_BODY_TEXT)

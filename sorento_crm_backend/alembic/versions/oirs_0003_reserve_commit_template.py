"""Order inquiry reserved email: "N line(s) still to reserve" (`PLAN-oi-request-cs-
reserve.md` section 6e.1, owner round 4, 24 Sep, AC-RS-80).

The commit route (`OrderInquiryReserveService.commit_request`) can now answer PART of a
request in one click and dispatch `order_inquiry_reserved` right away (R4-1: "the
reserved mail goes out on every Reserve click") rather than waiting for the whole
request to complete. The seeded `order_inquiry_reserved_default` body never told the
requester whether anything was left - this migration adds one line, printed only while
`reserve.open_row_count > 0` (falsy/absent renders nothing, so a completing commit, or
any OLDER dispatch context that carries no such key at all, is unchanged). Subject
untouched (AC-RS-80's own words).

Updates ``email_templates`` (code ``order_inquiry_reserved_default``) IN PLACE, same
`_set_template` shape `oihr_0002_undone_headline.py` uses for the identical reason: the
row already exists on every DB that ran `oirs_0001`, and the point of this migration is
to deliver a body fix, not a fresh seed. Idempotent - running twice sets the same body
both times. Downgrade restores round 1's own body verbatim (copied byte for byte from
`oirs_0001_reserve_requests.py`).

Revision ID: oirs_0003_reserve_commit_template
Revises: oirs_0002_reserve_round2
Create Date: 2026-09-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "oirs_0003_reserve_commit_template"
down_revision = "oirs_0002_reserve_round2"
branch_labels = None
depends_on = None


TEMPLATE_CODE = "order_inquiry_reserved_default"

_TH_STYLE = "border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;"
_TD_STYLE = "border:1px solid #d0d0d5;padding:4px 8px;"
_TABLE_STYLE = "border-collapse:collapse;font-family:Arial, sans-serif;font-size:13px;"

_SUBJECT = (
    "Reserved: {{ reserve.inquiry_no }} #{{ reserve.ordinal }} - {{ reserve.so_number }}"
)

# The line itself: `open_row_count` falsy (0, None, or the key absent on an OLDER
# dispatch context) prints nothing - `0 is not None` in Jinja truthiness is still
# falsy, so no `> 0` comparison is needed. Singular for exactly 1 (AC-RS-80's own
# "1 line still to reserve", never "1 lines").
_STILL_TO_RESERVE = (
    '{% if reserve.open_row_count %}<p>{{ reserve.open_row_count }} line'
    '{% if reserve.open_row_count != 1 %}s{% endif %} still to reserve.</p>{% endif %}'
)

_BODY_HTML = """\
<p>{{ actor.name if actor else '-' }} reserved stock for
{{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default("", true) }}).</p>
<table style="__TABLE_STYLE__">
  <thead>
    <tr>
      <th style="__TH_STYLE__">ITEM CODE</th><th style="__TH_STYLE__">QTY</th>
      <th style="__TH_STYLE__">REQUESTED</th><th style="__TH_STYLE__">RESERVED</th>
      <th style="__TH_STYLE__">BALANCE</th><th style="__TH_STYLE__">LOCATION</th>
      <th style="__TH_STYLE__">REASON</th>
    </tr>
  </thead>
  <tbody>
    {% for row in reserve.rows %}
    <tr>
      <td style="__TD_STYLE__">{{ row.item_code | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.qty | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.qty_requested | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.qty_reserved | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.remaining | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.location | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.reason | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
__STILL_TO_RESERVE__
<p>Reserved by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ reserve.link }}">Open in Order Inquiries</a></p>
""".replace("__TABLE_STYLE__", _TABLE_STYLE).replace("__TH_STYLE__", _TH_STYLE).replace(
    "__TD_STYLE__", _TD_STYLE
).replace("__STILL_TO_RESERVE__", _STILL_TO_RESERVE)

_BODY_TEXT = """\
{{ actor.name if actor else '-' }} reserved stock for {{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default("", true) }}).

ITEM CODE | QTY | REQUESTED | RESERVED | BALANCE | LOCATION | REASON
{% for row in reserve.rows %}{{ row.item_code | default("", true) }} | {{ row.qty | default("", true) }} | {{ row.qty_requested | default("", true) }} | {{ row.qty_reserved | default("", true) }} | {{ row.remaining | default("", true) }} | {{ row.location | default("", true) }} | {{ row.reason | default("", true) }}
{% endfor %}
{% if reserve.open_row_count %}{{ reserve.open_row_count }} line{% if reserve.open_row_count != 1 %}s{% endif %} still to reserve.
{% endif %}Reserved by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ reserve.link }}
"""


# --------------------------------------------------------------------------- #
# Round-1 body, copied byte for byte from oirs_0001_reserve_requests.py - what   #
# downgrade restores. Never edit this to "fix" it.                              #
# --------------------------------------------------------------------------- #

_PRE_BODY_HTML = """\
<p>{{ actor.name if actor else '-' }} reserved stock for
{{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default("", true) }}).</p>
<table style="__TABLE_STYLE__">
  <thead>
    <tr>
      <th style="__TH_STYLE__">ITEM CODE</th><th style="__TH_STYLE__">QTY</th>
      <th style="__TH_STYLE__">REQUESTED</th><th style="__TH_STYLE__">RESERVED</th>
      <th style="__TH_STYLE__">BALANCE</th><th style="__TH_STYLE__">LOCATION</th>
      <th style="__TH_STYLE__">REASON</th>
    </tr>
  </thead>
  <tbody>
    {% for row in reserve.rows %}
    <tr>
      <td style="__TD_STYLE__">{{ row.item_code | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.qty | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.qty_requested | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.qty_reserved | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.remaining | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.location | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ row.reason | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p>Reserved by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ reserve.link }}">Open in Order Inquiries</a></p>
""".replace("__TABLE_STYLE__", _TABLE_STYLE).replace("__TH_STYLE__", _TH_STYLE).replace(
    "__TD_STYLE__", _TD_STYLE
)

_PRE_BODY_TEXT = """\
{{ actor.name if actor else '-' }} reserved stock for {{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default("", true) }}).

ITEM CODE | QTY | REQUESTED | RESERVED | BALANCE | LOCATION | REASON
{% for row in reserve.rows %}{{ row.item_code | default("", true) }} | {{ row.qty | default("", true) }} | {{ row.qty_requested | default("", true) }} | {{ row.qty_reserved | default("", true) }} | {{ row.remaining | default("", true) }} | {{ row.location | default("", true) }} | {{ row.reason | default("", true) }}
{% endfor %}
Reserved by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ reserve.link }}
"""


def _set_template(bind, *, body_html: str, body_text: str) -> None:
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
                "subject": _SUBJECT,
                "body_html": body_html,
                "body_text": body_text,
            },
        )
        return
    # No row yet (this migration ran on a DB that skipped oirs_0001's own seed
    # somehow) - insert one rather than silently doing nothing.
    bind.execute(
        sa.text(
            """
            INSERT INTO email_templates (id, code, name, description, subject, body_html, body_text, is_active)
            VALUES (gen_random_uuid(), :code, :name, :description, :subject, :body_html, :body_text, true)
            """
        ),
        {
            "code": TEMPLATE_CODE,
            "name": "Order Inquiry Reserved by CS (default)",
            "description": (
                "Tells the requester what CS reserved, and the balance still to buy."
            ),
            "subject": _SUBJECT,
            "body_html": body_html,
            "body_text": body_text,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    _set_template(bind, body_html=_BODY_HTML, body_text=_BODY_TEXT)


def downgrade() -> None:
    bind = op.get_bind()
    _set_template(bind, body_html=_PRE_BODY_HTML, body_text=_PRE_BODY_TEXT)

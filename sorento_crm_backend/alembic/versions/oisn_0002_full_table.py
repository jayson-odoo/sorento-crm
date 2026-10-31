"""Reserve request / reserved emails as one flat full table (RESERVE-EMAIL-FULL-TABLE,
`documentation/plans/scm/reserve-email-full-table-acceptance-criteria.md`).

Data only, no schema change. The two seeded templates move from `oisn_0001_staged_notify`'s
grouped "bulk branch" to one flat table (OI NO first, one row per line, STATUS and an
optional REASON on the reserved email) on the wide layout. A row is updated IN PLACE only
while its subject AND layout still equal `oisn_0001`'s final values; an admin-edited template
is left alone (and still renders, the context keeps every key it read). Upgrade is
idempotent. Downgrade restores `oisn_0001`'s subject, layout and plain text only on a row
still holding this revision's values.

`oisn_0001`'s final values are frozen below (a migration must not import app code that keeps
changing).

Revision ID: oisn_0002_full_table
Revises: akn_0001_knowledge
Create Date: 2026-11-01
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "oisn_0002_full_table"
down_revision = "akn_0001_knowledge"
branch_labels = None
depends_on = None

# Built from two halves: several OI tests find THEIR seed migration by scanning alembic/versions
# for the full code as one token, and this file must not match.
REQUEST_CODE = "order_inquiry_reserve_requested" + "_default"
RESERVED_CODE = "order_inquiry_reserved" + "_default"

# oisn_0001_staged_notify's final subject / layout / plain text per template, frozen.
_PRIOR_JSON = json.loads(r'''{
 "request": {
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{% if reserve.requests %}{{ reserve.oi_count }} order inquiries need your reserve{% else %}Reserve request for {{ reserve.inquiry_no }} #{{ reserve.ordinal }}{% endif %}",
     "type": "heading"
    },
    {
     "text": "{% if reserve.requests %}{{ requester.name if requester else '-' }} asks CS to reserve stock on {{ reserve.oi_count }} order inquiries ({{ reserve.line_count }} lines).{% else %}{{ requester.name if requester else '-' }} asks CS to reserve stock for {{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default(\"\", true) }}).{% endif %}",
     "type": "intro"
    },
    {
     "html": "{% if reserve.requests %}<table width=\"100%\">\n  <thead>\n    <tr><th>OI NO</th><th>S/O NO</th><th>CUSTOMER</th><th>LINES</th></tr>\n  </thead>\n  <tbody>\n    {% for r in reserve.requests %}\n    <tr>\n      <td>{{ r.inquiry_no | default(\"\", true) }}</td>\n      <td>{{ r.so_number | default(\"\", true) }}</td>\n      <td>{{ r.customer | default(\"\", true) }}</td>\n      <td>{{ r.line_count | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{% if reserve.more_count %}<p>and {{ reserve.more_count }} more order inquir{{ 'y' if reserve.more_count == 1 else 'ies' }}.</p>{% endif %}<p>Requested by {{ requester.name if requester else '-' }} on {{ today }}.</p>{% else %}<table width=\"100%\">\n  <thead>\n    <tr>\n      <th>ITEM CODE</th><th>DELIVERY DATE</th>\n      <th>QTY</th><th>REMAINING</th>\n      <th>REQUESTED</th><th>LOCATION</th>\n    </tr>\n  </thead>\n  <tbody>\n    {% for row in reserve.rows %}\n    <tr>\n      <td>{{ row.item_code | default(\"\", true) }}</td>\n      <td>{{ row.delivery_date | default(\"\", true) }}</td>\n      <td>{{ row.qty | default(\"\", true) }}</td>\n      <td>{{ row.remaining | default(\"\", true) }}</td>\n      <td>{{ row.qty_requested | default(\"\", true) }}</td>\n      <td>{{ row.location | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{% if reserve.note %}<p>Note: {{ reserve.note }}</p>{% endif %}\n<p>Requested by {{ requester.name if requester else '-' }}{% if requester %} ({{ requester.email }}){% endif %} on {{ today }}.</p>{% endif %}",
     "type": "custom_text"
    },
    {
     "label": "{% if reserve.requests %}View order inquiries that need your reserve{% else %}Open in Order Inquiries{% endif %}",
     "type": "button",
     "url": "{{ reserve.link }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "subject": "{% if reserve.requests %}Reserve requests: {{ reserve.oi_count }} order inquiries ({{ requester.name if requester else '-' }}){% else %}Reserve request: {{ reserve.inquiry_no }} #{{ reserve.ordinal }} - {{ reserve.so_number }}{% endif %}",
  "text": "{% if reserve.requests %}{{ requester.name if requester else '-' }} asks CS to reserve stock on {{ reserve.oi_count }} order inquiries ({{ reserve.line_count }} lines).\n\nOI NO | S/O NO | CUSTOMER | LINES\n{% for r in reserve.requests %}{{ r.inquiry_no }} | {{ r.so_number }} | {{ r.customer }} | {{ r.line_count }}\n{% endfor %}{% if reserve.more_count %}and {{ reserve.more_count }} more order inquir{{ 'y' if reserve.more_count == 1 else 'ies' }}.\n{% endif %}Requested by {{ requester.name if requester else '-' }} on {{ today }}.\nView order inquiries that need your reserve: {{ reserve.link }}\n{% else %}{{ requester.name if requester else '-' }} asks CS to reserve stock for {{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default(\"\", true) }}).\n\nITEM CODE | DELIVERY DATE | QTY | REMAINING | REQUESTED | LOCATION\n{% for row in reserve.rows %}{{ row.item_code | default(\"\", true) }} | {{ row.delivery_date | default(\"\", true) }} | {{ row.qty | default(\"\", true) }} | {{ row.remaining | default(\"\", true) }} | {{ row.qty_requested | default(\"\", true) }} | {{ row.location | default(\"\", true) }}\n{% endfor %}\n{% if reserve.note %}Note: {{ reserve.note }}\n{% endif %}Requested by {{ requester.name if requester else '-' }} on {{ today }}.\nOpen: {{ reserve.link }}\n{% endif %}"
 },
 "reserved": {
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{% if reserve.requests %}CS answered your reserve requests on {{ reserve.oi_count }} order inquiries{% else %}Stock reserved for {{ reserve.inquiry_no }} #{{ reserve.ordinal }}{% endif %}",
     "type": "heading"
    },
    {
     "text": "{% if reserve.requests %}{{ actor.name if actor else '-' }} reserved stock on {{ reserve.oi_count }} order inquiries ({{ reserve.line_count }} lines). Check the balance still to buy.{% else %}{{ actor.name if actor else '-' }} reserved stock for {{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default(\"\", true) }}).{% endif %}",
     "type": "intro"
    },
    {
     "html": "{% if reserve.requests %}<table width=\"100%\">\n  <thead>\n    <tr><th>OI NO</th><th>S/O NO</th><th>CUSTOMER</th><th>LINES</th></tr>\n  </thead>\n  <tbody>\n    {% for r in reserve.requests %}\n    <tr>\n      <td>{{ r.inquiry_no | default(\"\", true) }}</td>\n      <td>{{ r.so_number | default(\"\", true) }}</td>\n      <td>{{ r.customer | default(\"\", true) }}</td>\n      <td>{{ r.line_count | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{% if reserve.more_count %}<p>and {{ reserve.more_count }} more order inquir{{ 'y' if reserve.more_count == 1 else 'ies' }}.</p>{% endif %}<p>Reserved by {{ actor.name if actor else '-' }} on {{ today }}.</p>{% else %}<table width=\"100%\">\n  <thead>\n    <tr>\n      <th>ITEM CODE</th><th>QTY</th>\n      <th>REQUESTED</th><th>RESERVED</th>\n      <th>BALANCE</th><th>LOCATION</th>\n      <th>REASON</th>\n    </tr>\n  </thead>\n  <tbody>\n    {% for row in reserve.rows %}\n    <tr>\n      <td>{{ row.item_code | default(\"\", true) }}</td>\n      <td>{{ row.qty | default(\"\", true) }}</td>\n      <td>{{ row.qty_requested | default(\"\", true) }}</td>\n      <td>{{ row.qty_reserved | default(\"\", true) }}</td>\n      <td>{{ row.remaining | default(\"\", true) }}</td>\n      <td>{{ row.location | default(\"\", true) }}</td>\n      <td>{{ row.reason | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{% if reserve.open_row_count %}<p>{{ reserve.open_row_count }} line{% if reserve.open_row_count != 1 %}s{% endif %} still to reserve.</p>{% endif %}\n<p>Reserved by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>{% endif %}",
     "type": "custom_text"
    },
    {
     "label": "{% if reserve.requests %}View reserved order inquiries{% else %}Open in Order Inquiries{% endif %}",
     "type": "button",
     "url": "{{ reserve.link }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "subject": "{% if reserve.requests %}Reserved: {{ reserve.oi_count }} order inquiries ({{ actor.name if actor else '-' }}){% else %}Reserved: {{ reserve.inquiry_no }} #{{ reserve.ordinal }} - {{ reserve.so_number }}{% endif %}",
  "text": "{% if reserve.requests %}{{ actor.name if actor else '-' }} reserved stock on {{ reserve.oi_count }} order inquiries ({{ reserve.line_count }} lines). Check the balance still to buy.\n\nOI NO | S/O NO | CUSTOMER | LINES\n{% for r in reserve.requests %}{{ r.inquiry_no }} | {{ r.so_number }} | {{ r.customer }} | {{ r.line_count }}\n{% endfor %}{% if reserve.more_count %}and {{ reserve.more_count }} more order inquir{{ 'y' if reserve.more_count == 1 else 'ies' }}.\n{% endif %}Reserved by {{ actor.name if actor else '-' }} on {{ today }}.\nView reserved order inquiries: {{ reserve.link }}\n{% else %}{{ actor.name if actor else '-' }} reserved stock for {{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default(\"\", true) }}).\n\nITEM CODE | QTY | REQUESTED | RESERVED | BALANCE | LOCATION | REASON\n{% for row in reserve.rows %}{{ row.item_code | default(\"\", true) }} | {{ row.qty | default(\"\", true) }} | {{ row.qty_requested | default(\"\", true) }} | {{ row.qty_reserved | default(\"\", true) }} | {{ row.remaining | default(\"\", true) }} | {{ row.location | default(\"\", true) }} | {{ row.reason | default(\"\", true) }}\n{% endfor %}\n{% if reserve.open_row_count %}{{ reserve.open_row_count }} line{% if reserve.open_row_count != 1 %}s{% endif %} still to reserve.\n{% endif %}Reserved by {{ actor.name if actor else '-' }} on {{ today }}.\nOpen: {{ reserve.link }}\n{% endif %}"
 }
}''')
_PRIOR = {REQUEST_CODE: _PRIOR_JSON["request"], RESERVED_CODE: _PRIOR_JSON["reserved"]}

_ASKER = "{{ requester.name if requester else '-' }}"
_ACTOR = "{{ actor.name if actor else '-' }}"
_BASE_COLS = ["OI NO", "SO DATE", "S/O NO", "ITEM CODE", "QTY", "REQUESTED RESERVE"]
_TAIL_COLS = ["DELIVERY DATE", "PROJECT/CUSTOMER"]
_STATUS_CELL = (
    "<td nowrap{% if l.status_kind == 'rejected' %} style=\"color:#B91C1C;font-weight:600;\""
    "{% elif l.status_kind == 'partial' %} style=\"color:#92400E;font-weight:600;\"{% endif %}>"
    "{{ l.status }}</td>"
)
_BUTTON_LABEL = (
    "{% if reserve.batch %}View these {{ reserve.oi_count }} order inquiries"
    "{% else %}View this order inquiry{% endif %}"
)
_REQUEST_INTRO = (
    f"{_ASKER} asks CS to reserve stock on {{{{ reserve.short }}}} ({{{{ reserve.lines_text }}}})."
)
_RESERVED_INTRO = (
    "{% if reserve.verdict == 'rejected' %}" + _ACTOR + " rejected {{ reserve.lines_text }} on {{ reserve.short }}."
    "{% elif reserve.verdict == 'mixed' %}" + _ACTOR + " answered {{ reserve.lines_text }} on {{ reserve.short }}: "
    "{% if reserve.full_count %}{{ reserve.full_count }} reserved, {% endif %}{{ reserve.tag }}."
    "{% else %}" + _ACTOR + " reserved {% if reserve.line_count != 1 %}all {% endif %}{{ reserve.lines_text }} "
    "on {{ reserve.short }}.{% endif %}"
)
_RESERVED_HEAD = (
    "{% if reserve.verdict == 'rejected' %}Rejected: {{ reserve.what }}"
    "{% else %}Reserved: {{ reserve.what }}{% if reserve.verdict == 'mixed' %}, {{ reserve.tag }}{% endif %}{% endif %}"
)
_RESERVED_HEADING = (
    "{% if reserve.verdict == 'rejected' %}Rejected: {{ reserve.short }}"
    "{% else %}Reserved: {{ reserve.short }}{% if reserve.verdict == 'mixed' %}, {{ reserve.tag }}{% endif %}{% endif %}"
)


def _table(answered: bool) -> str:
    heads = _BASE_COLS + (["STATUS"] if answered else []) + _TAIL_COLS
    th = "".join(f"<th>{h}</th>" for h in heads)
    cells = (
        "<td nowrap>{{ l.oi_no }}</td><td>{{ l.so_date }}</td><td>{{ l.so_number }}</td>"
        "<td>{{ l.item_code }}</td><td>{{ l.qty }}</td><td>{{ l.qty_requested }}</td>"
    )
    if answered:
        cells += _STATUS_CELL
    cells += "<td>{{ l.delivery_date }}</td><td>{{ l.project_customer }}</td>"
    if answered:
        th += '{% if reserve.show_reason %}<th style=\"min-width:120px;\">REASON</th>{% endif %}'
        cells += "{% if reserve.show_reason %}<td>{{ l.reason }}</td>{% endif %}"
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:12px;">'
        f'<thead><tr style="background:#F3F4F6;">{th}</tr></thead>'
        "<tbody>{% for l in reserve.lines %}<tr>" + cells + "</tr>{% endfor %}</tbody></table>"
    )


def _text_table(answered: bool) -> str:
    heads = _BASE_COLS + (["STATUS"] if answered else []) + _TAIL_COLS
    head = " | ".join(heads) + ("{% if reserve.show_reason %} | REASON{% endif %}" if answered else "")
    cells = [
        "{{ l.oi_no }}", "{{ l.so_date }}", "{{ l.so_number }}", "{{ l.item_code }}", "{{ l.qty }}",
        "{{ l.qty_requested }}",
    ]
    if answered:
        cells.append("{{ l.status }}")
    cells += ["{{ l.delivery_date }}", "{{ l.project_customer }}"]
    row = " | ".join(cells) + ("{% if reserve.show_reason %} | {{ l.reason }}{% endif %}" if answered else "")
    return head + "\n{% for l in reserve.lines %}" + row + "\n{% endfor %}"


_STILL = (
    "{% if reserve.open_row_count %}<p>{{ reserve.open_row_count }} line"
    "{% if reserve.open_row_count != 1 %}s{% endif %} still to reserve.</p>{% endif %}"
)
_NOTES = "{% for n in reserve.notes %}<p>Note ({{ n.inquiry_no }}): {{ n.text }}</p>{% endfor %}"
_STILL_TEXT = (
    "{% if reserve.open_row_count %}{{ reserve.open_row_count }} line"
    "{% if reserve.open_row_count != 1 %}s{% endif %} still to reserve.\n{% endif %}"
)
_NOTES_TEXT = "{% for n in reserve.notes %}Note ({{ n.inquiry_no }}): {{ n.text }}\n{% endfor %}"


def _subject(code: str) -> str:
    if code == REQUEST_CODE:
        return f"Reserve request{{{{ 's' if reserve.batch else '' }}}}: {{{{ reserve.what }}}} ({_ASKER})"
    return f"{_RESERVED_HEAD} ({_ACTOR})"


def _layout(code: str) -> dict:
    request = code == REQUEST_CODE
    if request:
        heading = "{{ reserve.short }} {{ 'need' if reserve.batch else 'needs' }} your reserve"
        intro = _REQUEST_INTRO
        html = _table(False) + _NOTES + _STILL + f"<p>Requested by {_ASKER} on {{{{ today }}}}.</p>"
    else:
        heading = _RESERVED_HEADING
        intro = _RESERVED_INTRO
        html = _table(True) + _STILL + f"<p>Answered by {_ACTOR} on {{{{ today }}}}.</p>"
    return {
        "version": 1,
        "width": "wide",
        "blocks": [
            {"type": "brand_header"},
            {"type": "heading", "text": heading},
            {"type": "intro", "text": intro},
            {"type": "custom_text", "html": html},
            {"type": "button", "label": _BUTTON_LABEL, "url": "{{ reserve.link }}"},
            {"type": "footer"},
        ],
    }


def _text(code: str) -> str:
    link = "{% if reserve.batch %}View these {{ reserve.oi_count }} order inquiries{% else %}View this order inquiry{% endif %}: {{ reserve.link }}\n"
    if code == REQUEST_CODE:
        return (
            f"{_REQUEST_INTRO}\n\n{_text_table(False)}\n{_NOTES_TEXT}{_STILL_TEXT}"
            f"Requested by {_ASKER} on {{{{ today }}}}.\n{link}"
        )
    return (
        f"{_RESERVED_INTRO}\n\n{_text_table(True)}\n{_STILL_TEXT}"
        f"Answered by {_ACTOR} on {{{{ today }}}}.\n{link}"
    )


def _swap(bind, code: str, *, old: dict, new: dict) -> None:
    """Move one template from `old` to `new` values, only while subject AND layout still
    equal `old`'s (and, when `old` names a plain text, that too)."""
    where = "code = :code AND subject = :subject AND layout_json = CAST(:layout AS jsonb)"
    params = {"code": code, "subject": old["subject"], "layout": json.dumps(old["layout"])}
    if old.get("guard_text"):
        where += " AND body_text = :guard_text"
        params["guard_text"] = old["text"]
    row = bind.execute(sa.text(f"SELECT id FROM email_templates WHERE {where}"), params).first()
    if row is None:
        return
    bind.execute(
        sa.text(
            "UPDATE email_templates SET subject = :subject, layout_json = CAST(:layout AS jsonb), "
            "body_text = :body_text WHERE id = :id"
        ),
        {
            "subject": new["subject"],
            "layout": json.dumps(new["layout"]),
            "body_text": new["text"],
            "id": row[0],
        },
    )


def _new(code: str) -> dict:
    return {"subject": _subject(code), "layout": _layout(code), "text": _text(code)}


def upgrade() -> None:
    bind = op.get_bind()
    for code in (REQUEST_CODE, RESERVED_CODE):
        _swap(bind, code, old=_PRIOR[code], new=_new(code))


def downgrade() -> None:
    bind = op.get_bind()
    for code in (REQUEST_CODE, RESERVED_CODE):
        _swap(bind, code, old={**_new(code), "guard_text": True}, new=_PRIOR[code])

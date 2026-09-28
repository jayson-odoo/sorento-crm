"""Email layout data (#1349, PLAN-email-layout-28sep.md S5/S6, AC-EM095/096).

(a) The six seeded automation templates get a block document (heading, their tables as
    custom text, one big button, footer) and a preheader - ONLY while ``layout_json`` is
    NULL and ``body_html`` is still byte-for-byte the seeded body (sha256 below, computed
    on 445cb1eb by replaying 212, oihe_0001, undo_0002, oihr_0001, oihr_0002, oirs_0001,
    oirs_0003, oihr_0003 and soatt_0001). A template an admin edited is left alone; it
    still renders branded through the implicit document. ``body_html`` and ``body_text``
    are never touched, so downgrade (which nulls what this set) restores the exact prior
    rendering.
(b) One ``email_templates`` row per system mail code (the hand-built mails that moved
    onto the layout), inserted only when the code is absent - never overwriting.

The documents are frozen copies of app/services/email_system_templates.py as of this
revision (a migration must not import app code that keeps changing).

Revision ID: eml_0002_seed_layouts
Revises: eml_0001_layout_columns
Create Date: 2026-09-28
"""
from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "eml_0002_seed_layouts"
down_revision = "eml_0001_layout_columns"
branch_labels = None
depends_on = None

# code STEM -> {sha256 of the seeded body_html, preheader, layout}. The stored key omits
# the codes' common "_default" suffix on purpose: several OI tests find THEIR seed migration
# by scanning alembic/versions for the full code as one token (see oihr_0001's TEMPLATE_CODE
# note), and this file must not be the second match. The runtime code is key + "_default".
SEEDED = json.loads(r'''{
 "order_inquiry_handover": {
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ handover.headline }}",
     "type": "heading"
    },
    {
     "html": "<table width=\"100%\">\n  <thead>\n    <tr><th>S/O NO</th><th>CUSTOMER</th><th>PROJECT</th></tr>\n  </thead>\n  <tbody>\n    {% for order in handover.orders %}\n    <tr>\n      <td>{{ order.so_number | default(\"\", true) }}</td>\n      <td>{{ order.customer | default(\"\", true) }}</td>\n      <td>{{ order.project | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{%- set cols = namespace(qty=false, delivery_date=false) -%}{%- for line in handover.lines -%}{%- if line.was and line.was.qty %}{% set cols.qty = true %}{% endif -%}{%- if line.was and line.was.delivery_date %}{% set cols.delivery_date = true %}{% endif -%}{%- endfor -%}<table width=\"100%\">\n  <thead>\n    <tr>\n      <th>SO DATE</th><th>S/O NO</th><th>LOCATION</th><th>ITEM CODE</th>\n      <th>QTY</th>{% if cols.qty %}<th>QTY CHANGE TO</th>{% endif %}\n      <th>DELIVERY DATE</th>{% if cols.delivery_date %}<th>DELIVERY DATE CHANGE TO</th>{% endif %}\n      <th>REMARK</th>\n    </tr>\n  </thead>\n  <tbody>\n    {% for line in handover.lines %}\n    <tr>\n      <td>{{ line.so_date | default(\"\", true) }}</td>\n      <td>{{ line.so_number | default(\"\", true) }}</td>\n      <td>{{ line.location | default(\"\", true) }}</td>\n      <td>{{ line.item_code | default(\"\", true) }}</td>\n      <td>{% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default(\"\", true) }}{% endif %}</td>\n      {% if cols.qty %}<td>{% if line.was and line.was.qty %}{{ line.qty | default(\"\", true) }}{% endif %}</td>{% endif %}\n      <td>{% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default(\"\", true) }}{% endif %}</td>\n      {% if cols.delivery_date %}<td>{% if line.was and line.was.delivery_date %}{{ line.delivery_date | default(\"\", true) }}{% endif %}</td>{% endif %}\n      <td>{{ line.remark | default(\"\", true) }}{% if line.attachments %}<br>Attachments: {% for a in line.attachments %}{% if not loop.first %}, {% endif %}{% if a.attached %}{{ a.name }}{% else %}<a href=\"{{ a.url }}\">{{ a.name }}</a> (not attached, too large for email){% endif %}{% endfor %}{% endif %}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n<p>Raised by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>",
     "type": "custom_text"
    },
    {
     "label": "Open in Order Inquiries",
     "type": "button",
     "url": "{{ handover.link }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "preheader": null,
  "sha256": "a5e4fdb73a1ace50805067998cfae4947ee2540d849210dd3dbbcfe8b310e439"
 },
 "order_inquiry_reserve_requested": {
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "Reserve request for {{ reserve.inquiry_no }} #{{ reserve.ordinal }}",
     "type": "heading"
    },
    {
     "text": "{{ requester.name if requester else '-' }} asks CS to reserve stock for {{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default(\"\", true) }}).",
     "type": "intro"
    },
    {
     "html": "<table width=\"100%\">\n  <thead>\n    <tr>\n      <th>ITEM CODE</th><th>DELIVERY DATE</th>\n      <th>QTY</th><th>REMAINING</th>\n      <th>REQUESTED</th><th>LOCATION</th>\n    </tr>\n  </thead>\n  <tbody>\n    {% for row in reserve.rows %}\n    <tr>\n      <td>{{ row.item_code | default(\"\", true) }}</td>\n      <td>{{ row.delivery_date | default(\"\", true) }}</td>\n      <td>{{ row.qty | default(\"\", true) }}</td>\n      <td>{{ row.remaining | default(\"\", true) }}</td>\n      <td>{{ row.qty_requested | default(\"\", true) }}</td>\n      <td>{{ row.location | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{% if reserve.note %}<p>Note: {{ reserve.note }}</p>{% endif %}\n<p>Requested by {{ requester.name if requester else '-' }}{% if requester %} ({{ requester.email }}){% endif %} on {{ today }}.</p>",
     "type": "custom_text"
    },
    {
     "label": "Open in Order Inquiries",
     "type": "button",
     "url": "{{ reserve.link }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "preheader": null,
  "sha256": "6fd0ca7e94caa1aba22e5538d5ea6ac9c69842a41ab829d59fb3f00ebb705f2f"
 },
 "order_inquiry_reserved": {
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "Stock reserved for {{ reserve.inquiry_no }} #{{ reserve.ordinal }}",
     "type": "heading"
    },
    {
     "text": "{{ actor.name if actor else '-' }} reserved stock for {{ reserve.inquiry_no }} #{{ reserve.ordinal }} ({{ reserve.so_number | default(\"\", true) }}).",
     "type": "intro"
    },
    {
     "html": "<table width=\"100%\">\n  <thead>\n    <tr>\n      <th>ITEM CODE</th><th>QTY</th>\n      <th>REQUESTED</th><th>RESERVED</th>\n      <th>BALANCE</th><th>LOCATION</th>\n      <th>REASON</th>\n    </tr>\n  </thead>\n  <tbody>\n    {% for row in reserve.rows %}\n    <tr>\n      <td>{{ row.item_code | default(\"\", true) }}</td>\n      <td>{{ row.qty | default(\"\", true) }}</td>\n      <td>{{ row.qty_requested | default(\"\", true) }}</td>\n      <td>{{ row.qty_reserved | default(\"\", true) }}</td>\n      <td>{{ row.remaining | default(\"\", true) }}</td>\n      <td>{{ row.location | default(\"\", true) }}</td>\n      <td>{{ row.reason | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{% if reserve.open_row_count %}<p>{{ reserve.open_row_count }} line{% if reserve.open_row_count != 1 %}s{% endif %} still to reserve.</p>{% endif %}\n<p>Reserved by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>",
     "type": "custom_text"
    },
    {
     "label": "Open in Order Inquiries",
     "type": "button",
     "url": "{{ reserve.link }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "preheader": null,
  "sha256": "794e72e73d6144d8fa7e57cc9733c3061dc3363783f74aabb34349f9f310966f"
 },
 "order_inquiry_undone": {
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{% if undo.headline == \"RECONSTRUCTED\" %}RECONSTRUCTED{% else %}{{ undo.headline | default(\"Undone\", true) }}{% endif %}: {{ undo.so_number | default(\"\", true) }} rev {{ undo.revision_no }}",
     "type": "heading"
    },
    {
     "html": "<p>{{ undo.customer | default(\"\", true) }}{% if undo.customer and undo.project %} / {% endif %}{{ undo.project | default(\"\", true) }}</p>\n<table width=\"100%\">\n  <thead>\n    <tr><th>ITEM CODE</th><th>QTY</th><th>DELIVERY DATE</th><th>OUTCOME</th></tr>\n  </thead>\n  <tbody>\n    {% for line in undo.lines %}\n    <tr>\n      <td>{{ line.item_code | default(\"\", true) }}</td>\n      <td>{{ line.qty | default(\"\", true) }}</td>\n      <td>{{ line.delivery_date | default(\"\", true) }}</td>\n      <td>{{ line.outcome | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n<p>Undone by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>",
     "type": "custom_text"
    },
    {
     "label": "Open in Order Inquiries",
     "type": "button",
     "url": "{{ undo.link }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "preheader": null,
  "sha256": "6c5435f4f84cf6428fca81b315b029e3404aee444fc8f713fe2e6d587ca0e065"
 },
 "purchase_request_approved": {
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ purchase_request.type_label }} {{ purchase_request.request_number }} approved",
     "type": "heading"
    },
    {
     "text": "Hi {{ recipient.name }},\n\n{{ purchase_request.type_label }} {{ purchase_request.request_number }} has been approved.",
     "type": "intro"
    },
    {
     "rows": [
      {
       "label": "Customer",
       "value": "{{ purchase_request.customer_name or '-' }}"
      },
      {
       "label": "Project",
       "value": "{{ purchase_request.project_title or '-' }}"
      },
      {
       "label": "Purpose",
       "value": "{{ purchase_request.purpose or '-' }}"
      },
      {
       "label": "Requested by",
       "value": "{{ purchase_request.requested_by or '-' }}"
      },
      {
       "label": "Approved by",
       "value": "{{ purchase_request.approved_by or '-' }}"
      },
      {
       "label": "Approved at",
       "value": "{{ purchase_request.approved_at or '-' }}"
      },
      {
       "label": "Expected delivery",
       "value": "{{ purchase_request.expected_delivery_date or '-' }}"
      },
      {
       "label": "Expected PO date",
       "value": "{{ purchase_request.expected_po_date or purchase_request.expected_po_date_text or '-' }}"
      }
     ],
     "type": "facts"
    },
    {
     "html": "{% if purchase_request.approval_comments %}<p><strong>Approval comments:</strong> {{ purchase_request.approval_comments }}</p>{% endif %}",
     "type": "custom_text"
    },
    {
     "label": "Open purchase request",
     "type": "button",
     "url": "{{ purchase_request.link }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "preheader": "Approved by {{ purchase_request.approved_by or '-' }} for {{ purchase_request.customer_name or '-' }}.",
  "sha256": "9afca8114e23764983ed5863f45fba6d1d772f56752ad104698a2978247b5caf"
 },
 "sponsorship_form_approved": {
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ purchase_request.type_label }} {{ purchase_request.request_number }} approved",
     "type": "heading"
    },
    {
     "text": "Hi {{ recipient.name }},\n\n{{ purchase_request.type_label }} {{ purchase_request.request_number }} has been approved.",
     "type": "intro"
    },
    {
     "rows": [
      {
       "label": "Customer",
       "value": "{{ purchase_request.customer_name or '-' }}"
      },
      {
       "label": "Project",
       "value": "{{ purchase_request.project_title or '-' }}"
      },
      {
       "label": "Purpose",
       "value": "{{ purchase_request.purpose or '-' }}"
      },
      {
       "label": "Total project value",
       "value": "{{ purchase_request.total_project_value_text or purchase_request.total_project_value or '-' }}"
      },
      {
       "label": "Requested by",
       "value": "{{ purchase_request.requested_by or '-' }}"
      },
      {
       "label": "Approved by",
       "value": "{{ purchase_request.approved_by or '-' }}"
      },
      {
       "label": "Approved at",
       "value": "{{ purchase_request.approved_at or '-' }}"
      }
     ],
     "type": "facts"
    },
    {
     "html": "{% if purchase_request.approval_comments %}<p><strong>Approval comments:</strong> {{ purchase_request.approval_comments }}</p>{% endif %}",
     "type": "custom_text"
    },
    {
     "label": "Open sponsorship form",
     "type": "button",
     "url": "{{ purchase_request.link }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "preheader": "Approved by {{ purchase_request.approved_by or '-' }} for {{ purchase_request.customer_name or '-' }}.",
  "sha256": "a9e7175c78523fd84204a9f8f4915a2416455537729bbf100de38443202b27c8"
 }
}''')

# code -> {name, description, subject, preheader, body_text, layout}
SYSTEM = json.loads(r'''{
 "account_email_changed": {
  "body_text": null,
  "description": "Sent to the NEW address when an admin changes a user's sign-in email.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "Your sign-in email was updated",
     "type": "heading"
    },
    {
     "text": "Hello,\n\nAn administrator updated the email you use to sign in to {{ company.name }}. Your password is unchanged.",
     "type": "intro"
    },
    {
     "rows": [
      {
       "label": "Previous",
       "value": "{{ old_email }}"
      },
      {
       "label": "New",
       "value": "{{ new_email }}"
      }
     ],
     "type": "facts"
    },
    {
     "label": "Sign in",
     "type": "button",
     "url": "{{ sign_in_link }}"
    },
    {
     "html": "<p>If you did not expect this change, contact your administrator immediately.</p>",
     "type": "custom_text"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Sign-in email updated",
  "preheader": "Your password is unchanged.",
  "subject": "Your sign-in email was updated"
 },
 "attachment_linked": {
  "body_text": null,
  "description": "Notifies an uploader (or the explicit notify user) when an external API used their file(s) to create or link an entity - product photo, form, packing list. Multiple callbacks within the coalesce window re-render this with every attachment collected so far.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ title }}",
     "type": "heading"
    },
    {
     "html": "{{ summary_html }}",
     "type": "custom_text"
    },
    {
     "label": "{{ entity_link_text }}",
     "type": "button",
     "url": "{{ entity_url }}"
    },
    {
     "html": "{% if attachment_items %}<p>Your attachment(s):</p><ul>{% for a in attachment_items %}<li><a href=\"{{ a.url }}\">{{ a.name }}</a></li>{% endfor %}</ul>{% endif %}",
     "type": "custom_text"
    },
    {
     "note": "This is a system-generated email. Please do not reply.",
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Attachment linked (external)",
  "preheader": null,
  "subject": "{{ title }}"
 },
 "complaint_created": {
  "body_text": "Dear Complaint Team,\n\n{{ sentence }}\n\n{{ view_url }}\n\nThis is a system-generated email. Please do not reply.",
  "description": "Notifies the Complaint team when a new complaint is created externally, or a previously rejected one is resubmitted.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ title }}",
     "type": "heading"
    },
    {
     "text": "Dear Complaint Team,\n\n{{ sentence }}",
     "type": "intro"
    },
    {
     "label": "Open complaint",
     "type": "button",
     "url": "{{ view_url }}"
    },
    {
     "note": "This is a system-generated email. Please do not reply.",
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Complaint created / resubmitted",
  "preheader": null,
  "subject": "{{ title }}"
 },
 "complaint_do_delivered": {
  "body_text": "Dear Complaint Team,\n\n{{ headline }}{% if items_block %}\n\n{{ items_block }}{% endif %}\n\n{{ view_url }}\n\nThis is a system-generated email. Please do not reply.",
  "description": "Notifies the Complaint team (Tier 1 + 2) that a replacement DO has been delivered.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ title }}",
     "type": "heading"
    },
    {
     "text": "Dear Complaint Team,\n\n{{ headline }}",
     "type": "intro"
    },
    {
     "html": "{% if item_lines %}<p>Items delivered:</p><ul>{% for l in item_lines %}<li>{{ l }}</li>{% endfor %}</ul>{% endif %}",
     "type": "custom_text"
    },
    {
     "label": "Open complaint",
     "type": "button",
     "url": "{{ view_url }}"
    },
    {
     "note": "This is a system-generated email. Please do not reply.",
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Replacement delivery order delivered",
  "preheader": null,
  "subject": "{{ title }}"
 },
 "notification_generic": {
  "body_text": null,
  "description": "Any notification that has a title and a body but no template of its own.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ title }}",
     "type": "heading"
    },
    {
     "text": "{{ body }}",
     "type": "intro"
    },
    {
     "label": "{{ link_label | default('Open in Sorento', true) }}",
     "type": "button",
     "url": "{{ link }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Notification (generic)",
  "preheader": null,
  "subject": "{{ title }}"
 },
 "onboarding_completed": {
  "body_text": null,
  "description": "Sent to the requester once every approved person in the batch has been processed.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "Onboarding complete",
     "type": "heading"
    },
    {
     "text": "Hello {{ requester_name }},\n\nYour onboarding submission '{{ request_title }}' has been processed.",
     "type": "intro"
    },
    {
     "hide_empty": false,
     "rows": [
      {
       "label": "Accounts created",
       "value": "{{ created }}"
      },
      {
       "label": "Already existed",
       "value": "{{ skipped }}"
      }
     ],
     "type": "facts"
    },
    {
     "rows": [
      {
       "label": "Could not be created",
       "value": "{{ failed if failed else '' }}"
      }
     ],
     "type": "facts"
    },
    {
     "html": "{% if failed %}<p>Somebody from the team will be in touch about the ones that failed.</p>{% endif %}<p>Anybody who received an account has been emailed a link to set their password.</p>",
     "type": "custom_text"
    },
    {
     "note": "This is a system-generated email. Please do not reply.",
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Onboarding completed",
  "preheader": null,
  "subject": "Onboarding complete: {{ request_title }}"
 },
 "onboarding_submitted": {
  "body_text": null,
  "description": "Confirms to the requester that their onboarding batch was received.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "We received your submission",
     "type": "heading"
    },
    {
     "text": "Hello {{ requester_name }},\n\nWe have received your onboarding submission '{{ request_title }}' with {{ people_count }} {{ 'person' if people_count == 1 else 'people' }}.\n\nSomebody will review it and you will get one more email when it is done. Your original link now shows the status of each person.",
     "type": "intro"
    },
    {
     "note": "This is a system-generated email. Please do not reply.",
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Onboarding submitted",
  "preheader": null,
  "subject": "Received: {{ request_title }}"
 },
 "promotion_created": {
  "body_text": null,
  "description": "Notifies an uploader (or the explicit notify user) when an external API created a promotion using their file(s).",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ title }}",
     "type": "heading"
    },
    {
     "html": "{{ summary_html }}",
     "type": "custom_text"
    },
    {
     "label": "{{ entity_link_text }}",
     "type": "button",
     "url": "{{ entity_url }}"
    },
    {
     "html": "{% if attachment_items %}<p>Your attachment(s):</p><ul>{% for a in attachment_items %}<li><a href=\"{{ a.url }}\">{{ a.name }}</a></li>{% endfor %}</ul>{% endif %}",
     "type": "custom_text"
    },
    {
     "note": "This is a system-generated email. Please do not reply.",
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Promotion created (external)",
  "preheader": null,
  "subject": "{{ title }}"
 },
 "purchase_request_requester_approved": {
  "body_text": null,
  "description": "Sent to the user who requested approval when the purchase request or sponsorship form is approved.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ purchase_request.type_label }} approved",
     "type": "heading"
    },
    {
     "text": "Your {{ purchase_request.type_label|lower }} has been approved.",
     "type": "intro"
    },
    {
     "rows": [
      {
       "label": "Reference",
       "value": "{{ purchase_request.request_number }}"
      },
      {
       "label": "Project",
       "value": "{{ purchase_request.project_title }}"
      }
     ],
     "type": "facts"
    },
    {
     "label": "View form",
     "type": "button",
     "url": "{{ view_url }}"
    },
    {
     "label": "Or paste this link into your browser:",
     "type": "link",
     "url": "{{ view_url }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Purchase request / sponsorship form approved (requester)",
  "preheader": "{{ purchase_request.type_label }} {{ purchase_request.request_number }} has been approved.",
  "subject": "{{ purchase_request.type_label }} approved"
 },
 "purchase_request_requester_rejected": {
  "body_text": null,
  "description": "Sent to the user who requested approval when the purchase request or sponsorship form is rejected.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ purchase_request.type_label }} rejected",
     "type": "heading"
    },
    {
     "text": "Your {{ purchase_request.type_label|lower }} has been rejected.",
     "type": "intro"
    },
    {
     "rows": [
      {
       "label": "Reference",
       "value": "{{ purchase_request.request_number }}"
      },
      {
       "label": "Project",
       "value": "{{ purchase_request.project_title }}"
      }
     ],
     "type": "facts"
    },
    {
     "label": "View form",
     "type": "button",
     "url": "{{ view_url }}"
    },
    {
     "label": "Or paste this link into your browser:",
     "type": "link",
     "url": "{{ view_url }}"
    },
    {
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Purchase request / sponsorship form rejected (requester)",
  "preheader": "{{ purchase_request.type_label }} {{ purchase_request.request_number }} has been rejected.",
  "subject": "{{ purchase_request.type_label }} rejected"
 },
 "purchase_request_submitted": {
  "body_text": null,
  "description": "Sent to the Project Sales team, one email to all, when a purchase request or sponsorship form is created or updated by an external integration.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ heading }}",
     "type": "heading"
    },
    {
     "text": "Dear Project Sales Team,\n\n{{ intro }}",
     "type": "intro"
    },
    {
     "rows": [
      {
       "label": "Reference",
       "value": "{{ purchase_request.request_number }}"
      },
      {
       "label": "Project",
       "value": "{{ purchase_request.project_title }}"
      }
     ],
     "type": "facts"
    },
    {
     "label": "Open request",
     "type": "button",
     "url": "{{ view_url }}"
    },
    {
     "note": "This is a system-generated email. Please do not reply.",
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Purchase request / sponsorship form submitted",
  "preheader": "{{ intro | truncate(140, true, '...', 0) }}",
  "subject": "{{ heading }}"
 },
 "sla_daily_summary": {
  "body_text": null,
  "description": "Daily digest of a staff member's outstanding assigned conversations.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "Your daily SLA summary",
     "type": "heading"
    },
    {
     "text": "Hi{% if recipient.name %} {{ recipient.name }}{% endif %},\n\nHere is where your conversations stand today, {{ summary_date }}.",
     "type": "intro"
    },
    {
     "hide_empty": false,
     "rows": [
      {
       "label": "Outstanding today",
       "value": "{{ outstanding_count }}"
      },
      {
       "label": "Last 7 days",
       "value": "{{ responded_7 }} responded, {{ resolved_7 }} resolved"
      },
      {
       "label": "Last 30 days",
       "value": "{{ responded_30 }} responded, {{ resolved_30 }} resolved"
      }
     ],
     "type": "facts"
    },
    {
     "html": "<h3>Outstanding conversations</h3><table width=\"100%\"><thead><tr><th>Name</th><th>Phone</th><th>Conversation</th></tr></thead><tbody>{% for c in conversations %}<tr><td>{{ c.name }}</td><td>{{ c.phone }}</td><td><a href=\"{{ c.link }}\">Open</a></td></tr>{% else %}<tr><td colspan=\"3\">No outstanding assigned conversations.</td></tr>{% endfor %}</tbody></table>",
     "type": "custom_text"
    },
    {
     "label": "Open my SLA tracking",
     "type": "button",
     "url": "{{ summary_link }}"
    },
    {
     "html": "<p style=\"font-size:13px;color:#6b7280;text-align:center;\">Thanks for your help in making {{ company.name }} a better place to work. <a href=\"{{ unsubscribe_link }}\">Unsubscribe from this daily summary</a></p>",
     "type": "custom_text"
    },
    {
     "note": "You receive this summary because you subscribed to the daily SLA summary.",
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Daily SLA summary",
  "preheader": "{{ outstanding_count }} outstanding conversation{% if outstanding_count != 1 %}s{% endif %} as of {{ summary_date }}.",
  "subject": "Your daily SLA summary ({{ summary_date }})"
 },
 "stock_inquiry_created": {
  "body_text": null,
  "description": "Sent to a team (e.g. purchasing) one email to all when a stock inquiry needs its review.",
  "layout": {
   "blocks": [
    {
     "type": "brand_header"
    },
    {
     "text": "{{ heading }}",
     "type": "heading"
    },
    {
     "text": "{{ intro }}",
     "type": "intro"
    },
    {
     "label": "Open stock inquiry",
     "type": "button",
     "url": "{{ view_url }}"
    },
    {
     "note": "This is a system-generated email. Please do not reply.",
     "type": "footer"
    }
   ],
   "version": 1
  },
  "name": "Stock inquiry team notice",
  "preheader": "{{ intro | truncate(140, true, '...', 0) }}",
  "subject": "{{ heading }}"
 }
}''')


_SUFFIX = "_default"


def _custom_html(layout: dict) -> str:
    return "\n".join(b.get("html") or "" for b in layout["blocks"] if b.get("type") == "custom_text" and b.get("html"))


def upgrade() -> None:
    bind = op.get_bind()
    for stem, spec in SEEDED.items():
        code = stem + _SUFFIX
        row = bind.execute(
            sa.text("SELECT id, body_html, layout_json FROM email_templates WHERE code = :code"),
            {"code": code},
        ).first()
        if row is None or row[2] is not None:
            continue
        if hashlib.sha256((row[1] or "").encode("utf-8")).hexdigest() != spec["sha256"]:
            continue
        bind.execute(
            sa.text(
                "UPDATE email_templates SET layout_json = CAST(:layout AS jsonb), preheader = :pre "
                "WHERE id = :id AND layout_json IS NULL"
            ),
            {"layout": json.dumps(spec["layout"]), "pre": spec.get("preheader"), "id": row[0]},
        )

    for code, spec in SYSTEM.items():
        bind.execute(
            sa.text(
                "INSERT INTO email_templates "
                "(id, code, name, description, subject, body_html, body_text, preheader, layout_json, is_active, created_at, updated_at) "
                "SELECT gen_random_uuid(), :code, :name, :description, :subject, :body_html, :body_text, :pre, "
                "CAST(:layout AS jsonb), true, now(), now() "
                "WHERE NOT EXISTS (SELECT 1 FROM email_templates WHERE code = :code)"
            ),
            {
                "code": code,
                "name": spec["name"],
                "description": spec["description"],
                "subject": spec["subject"],
                "body_html": _custom_html(spec["layout"]),
                "body_text": spec.get("body_text"),
                "pre": spec.get("preheader"),
                "layout": json.dumps(spec["layout"]),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    # (b) only rows still exactly as seeded here (never an admin-edited one).
    for code, spec in SYSTEM.items():
        bind.execute(
            sa.text(
                "DELETE FROM email_templates WHERE code = :code AND subject = :subject "
                "AND layout_json = CAST(:layout AS jsonb) "
                "AND NOT EXISTS (SELECT 1 FROM automations a WHERE a.email_template_id = email_templates.id)"
            ),
            {"code": code, "subject": spec["subject"], "layout": json.dumps(spec["layout"])},
        )
    # (a) only rows still carrying the document set here.
    for stem, spec in SEEDED.items():
        code = stem + _SUFFIX
        bind.execute(
            sa.text(
                "UPDATE email_templates SET layout_json = NULL, preheader = NULL "
                "WHERE code = :code AND layout_json = CAST(:layout AS jsonb)"
            ),
            {"code": code, "layout": json.dumps(spec["layout"])},
        )

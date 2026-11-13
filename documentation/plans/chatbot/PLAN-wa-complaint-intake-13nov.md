# PLAN: WhatsApp complaint intake via the ideation path (typed submissions)

Status: Plan, behaviour card posted as crew-ask (PR #2400), waiting on owner answers. Track: L (lead pattern).
Lane: WA-COMPLAINT-INTAKE. Owner ask 13 Nov 2026, demo Mon 16 Nov 09:30.

## Goal

Generalise the WhatsApp ideation path into typed submissions (type = idea | complaint | later types, one
shared path). A dealer reports a complaint on WhatsApp; the bot gathers what a complaint needs, shows a
confirm summary, and on "yes" creates the complaint in the CRM complaints module through the existing
create function, linked back to the conversation; CS is notified as usual.

## Discovery (what exists, file:line)

The ideation path on WhatsApp has two halves today:

| Piece | Where | Who can use it |
|---|---|---|
| Bot lane `ideate` -> MCP `crm_ideation_turn` -> `/external/ideation/turn` -> `handle_capture_turn` | `lanes/ideate.py:224`, `api/v1/external/ideation.py:33`, `ideation_capture_service.py:244` | only a contact LINKED to an active CRM user holding `ideation.board.view` (`ideation_capture_service.py:186`) |
| Agent write `crm_idea_create`: propose -> confirm summary -> "yes" -> create | `agent/writes.py:2108`, `:2262`, confirm block `agent/loop.py:866` | linked CRM users |
| Agent dealer writes (contact principal): `crm_stock_inquiry_create`, notes, withdraw | `agent/portal_writes.py:30`, `_si_execute :390` | dealers (contacts with AI access) whose portal form is switched on (`portal_form_visibility_service`) |

Dealers cannot use the ideate lane (no linked user). The dealer-capable half of the path is the agent's
propose -> confirm -> write seam, which already runs the PORTAL's own service as the contact. The earlier
plan named the complaint claim as its slice 2 (`documentation/plans/resources/PLAN-agentic-wa-w2-01nov.md`
lines 57, 98).

Where a complaint lands and who is told:

| Function | file:line | Reuse |
|---|---|---|
| Portal draft + submit as the contact (creates the `complaints` row, assigns the number, sets `respond_inbox_url` = link back to the WhatsApp conversation) | `portal_service.py:1106` draft, `:1153` submit, `:1523` `_instantiate`, `:1414` number | reuse as is (dealer) |
| Required fields on submit (12, incl. DO number and product lines) | `portal_required_fields.py:19` | reuse as is |
| CS notification on submit (Tier 1 complaint team: in-app + one email) | `portal_service.py:2051` -> `complaints_service.py:1326` `notify_team_complaint_external_created` | reuse as is |
| Staff create (CRM form) | `api/v1/complaints/complaints.py:1074` -> `complaints_service.py:1865` `create_complaint` | reuse for the staff variant only (Q2) |
| Dealer's DO lookup (DO number, debtor, product lines) | `api/v1/public/portal.py:646` | extract the query into one shared function, called by the portal route and the bot |
| Option lists: complaint type, defects discovered, within warranty, customer type | lookup sets `complaints_*` (`public/portal.py:474`) | reuse as is |
| Photos onto the complaint | `entity_attachment_service.py:255` `create_attachment_and_link`; WhatsApp media rows `models/media.py:179` `MediaExtractionJob.media_url`; byte fetch `media_extract/service.py:201` | reuse as is |
| Stock inquiry draft+submit+cleanup | `portal_writes.py:390-434` | turn into ONE shared "submit a portal form as the contact" function; stock inquiry and complaint both call it |
| Router: a turn with media always goes to the bot | `router.py:78` | extend (Q4) |

## Behaviour card

See the crew-ask on PR #2400 (copied below once answered).

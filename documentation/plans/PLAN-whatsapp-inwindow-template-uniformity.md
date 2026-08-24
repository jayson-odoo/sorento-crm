# PLAN - In-window template uniformity for Respond.io auto-sends

**Status:** In progress (2026-06-21)
**Branch:** `feature/whatsapp-inwindow-template-uniformity`
**Builds on:** `documentation/plans/PLAN-whatsapp-template-fallback.md` (the 24h-window text-vs-template choke point)

## Goal

Every CRM auto-send to a Respond.io contact reads **identically** whether it goes
out inside the 24h WhatsApp window (free text today) or outside it (approved
template today). Today the out-of-window branch renders the use-case's configured
template (`body_text` + resolved params); the in-window branch sends whatever
ad-hoc `text` the caller built. This plan makes the **in-window branch render from
the same template**, so the message structure is uniform across both branches.

## Decisions (locked with stakeholder 2026-06-21)

- **Formatting fidelity = richer multiline.** In-window we render the same
  template body with the same variables, but variable values keep their newlines
  (free text allows them; the WhatsApp template branch flattens `\n` → `" | "`).
  Structure is uniform; in-window just reads cleaner. → `sanitize_param(..., flatten=False)`.
- **Scope = core use-cases that already route through `send_text_or_template`:**
  `complaint`, `stock_inquiry`, `purchase_request`, `sponsorship_form`,
  `portal_otp`, `sla_daily_summary`, **+ `sla_assignment`, `sla_escalation`**
  (already sent through the choke point via `notification_tasks`, but not yet in
  the configurable use-case enum - added here so an admin can give them a template).
- **Fallback is preserved.** When a use-case has no valid configured default
  template, the in-window branch sends the caller's raw `text` exactly as today.
  Uniformity therefore rolls out **per use-case as templates are configured** - 
  zero behaviour change until a default exists. Same safety as the out-of-window
  `TemplateSendSkipped` path, but in-window degrades to text instead of failing.
- **Out of scope (this pass):** the 2 ad-hoc auto-sends that bypass the choke
  point (portal-link send `portal_service.py:317`, ticket status
  `ticket_notification_service.py:197`) and all human-typed chat sends
  (activities / sla manual reply) - those stay free-form by design.

## Background (verified)

- Choke point: `app/services/respond_messaging_service.py::send_text_or_template`.
  In-window → `RespondClient().send_message(identifier, text)`; out-of-window →
  `send_template_for_use_case` (renders the default template).
- Renderer already exists: `app/services/respond_chat_template_service.py::render_filled_body(body_text, params)`
  substitutes `{{1}}..{{n}}`.
- Param resolution already exists: `resolve_template_params(param_mapping, param_count, context_vars)`
  + `sanitize_param` (currently always flattens newlines).
- Default templates: `respond_template_defaults` (one row per use-case →
  `template_id` + `param_mapping`). `get_default_row` / `serialize_default` /
  validity in `app/services/respond_template_service.py`.
- Use-case enum: `app/models/respond_template.py::TEMPLATE_DEFAULT_USE_CASES`
  (6 entries; missing `sla_assignment` / `sla_escalation`).
- Allowed param vars: `PARAM_VARIABLES` - already includes `contact_name` and
  `message`, enough for a basic SLA template; granular SLA vars (tier/due) can be
  a follow-up.

## Changes

### Backend

1. `respond_messaging_service.py`
 - `sanitize_param(value, *, max_len, flatten=True)` - when `flatten=False`,
     preserve newlines (tabs→space, length-bound only).
 - `resolve_template_params(..., flatten=True)` - thread the flag to the sanitizer.
 - New `render_in_window_text(db, *, use_case, context_vars, fallback_text) -> str`
   - resolve the default template; if invalid/missing return `fallback_text`;
     else `render_filled_body(template.body_text, resolve_template_params(..., flatten=False))`.
 - `send_text_or_template` - compute `vars_resolved` (with `message` / `portal_url`
     defaulting) **once, before** the window branch so in/out-of-window resolve
     variables identically. In-window: send `render_in_window_text(...)` instead of
     raw `text`; stamp the rendered string into `request_payload` + the returned
     `text`. Keep `sent_as: "text"`.
2. `respond_template.py` - add `"sla_assignment"`, `"sla_escalation"` to
   `TEMPLATE_DEFAULT_USE_CASES`.

### Frontend

- None required for the core. The template-defaults admin config is enum-driven;
  the 2 new use-cases surface automatically. Verify they render + are configurable.

## Tests (pytest)

- In-window with a configured default → message is the rendered template body
  (not the raw text), variables substituted.
- In-window with NO default → raw `text` sent unchanged (fallback).
- Richer multiline: a param value containing `\n` keeps the newline in-window but
  flattens to `" | "` out-of-window (same template, both branches).
- `vars_resolved` parity: `message` / `portal_url` defaulting applies in-window.
- Existing `send_text_or_template` / window tests stay green.

## Rollout

Incremental and reversible. No template configured ⇒ identical to today. Admins
opt each use-case into uniformity by setting its default template. Revert =
in-window branch sends raw `text` again (single-function change).

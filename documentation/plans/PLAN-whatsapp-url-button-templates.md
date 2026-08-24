# PLAN - WhatsApp URL-button templates for Respond.io auto-sends

**Status:** Implemented (backend + admin modal + tests, 2026-06-22). Pending: dynamic
template approved in Meta (static→dynamic recreate done locally), browser-verify modal,
prod send check once approved.
**Branch:** `feature/whatsapp-url-button-templates` (not yet cut)
**Builds on:** `PLAN-whatsapp-template-fallback.md` (24h window text-vs-template choke point),
`PLAN-whatsapp-inwindow-template-uniformity.md` (in-window renders same template body).

## Problem (verified in prod)

Complaint technical-response update sent **out of window** (template branch). Two defects:

1. **`| ` newline noise.** The full multi-line update is stuffed into one body
   variable (`{{3}} = message`). WhatsApp **hard-rejects** `\n` / tab / 4+ spaces
   inside template body params, so `sanitize_param(flatten=True)` rewrites newlines
   to `" | "` (`respond_messaging_service.py:79-82`). Reads as one confusing run-on.
2. **Dead portal link.** The portal URL is appended into the same `{{3}}` variable.
   WhatsApp does **not** auto-linkify URLs delivered via a template *variable*
   (only free-session text and template **buttons** linkify). So the link is plain
   unclickable text.

In-window sends (free text, `flatten=False`) already read cleanly with real newlines
and a clickable URL - the defects only bite when the contact's 24h window is closed.

## What a URL button can and cannot fix

- **CAN fix:** the dead link. A template dynamic-URL **button** renders as a tappable
  "View complaint" CTA, always clickable, out of window.
- **CANNOT fix:** newlines inside body variables. That is a Meta platform limit on
  template parameters, independent of buttons. Mitigation only: since the URL no
  longer sits inline, flatten body newlines to a **single space** (clean paragraph)
  instead of `" | "`.

## Hard prerequisites (user-side - cannot be done in code)

1. **Create + get approved** a WhatsApp template (UTILITY) for the `complaint`
   use case with:
   - a short body (e.g. `Hi {{1}}, update on complaint {{2}}: {{3}}`), and
   - **one dynamic URL button**: base `https://fe-sorento.foundryx.my/` + `{{1}}`
     suffix (Meta allows exactly one dynamic suffix var per URL button).
2. **Provide the "Copy API Payload" JSON** from respond.io Template Manager for that
   approved template. ✅ Provided 2026-06-22 - button-component shape locked (below).
   BUT the pasted template (`update_with_button`) has a **STATIC** button
   (`url: https://fe-sorento.foundryx.my/`, `parameters: []`) → homepage only,
   cannot deep-link per complaint. **Must be recreated as DYNAMIC** (URL
   `https://fe-sorento.foundryx.my/{{1}}`, suffix passed at send) and re-approved
   before build.

Until the dynamic template is approved, backend work is design-only.

## Locked button-component shape (respond.io, from Copy API Payload 2026-06-22)

respond.io does **NOT** use Meta's `{"type":"button","sub_type":"url","index":n}`
form. It wraps buttons in a single `buttons` component:

```json
{"type":"buttons","buttons":[
  {"type":"url","text":"View complaint",
   "url":"https://fe-sorento.foundryx.my/{{1}}",
   "parameters":[{"type":"text","text":"<dynamic suffix>"}]}]}
```

`send_template_message` appends this component (after `body`) when the default's
template has a dynamic URL button. Suffix = resolved `portal_url` minus the button's
base prefix (everything before `{{1}}` in the stored `url`).

## Decisions (locked with stakeholder 2026-06-22)

- **D1 - In-window = decouple (rich free text).** In-window keeps sending the full
  detailed update as free text (real newlines + clickable URL, no button).
  Template+button used only out of window. Buttons don't render in free text anyway.
  → window-open branch in `send_text_or_template` sends the rich `text` directly for
  button use-cases (skip `render_in_window_text`).
- **D2 - Body flatten char.** `" | "` → `" "` (space) now the URL is not inline.
- **D3 - Scope.** Complaint first; same mechanism later for `stock_inquiry` /
  `purchase_request` / `sponsorship_form` (all route through the same choke point).
- **Template exists.** Stakeholder has an approved URL-button template; will paste
  the respond.io "Copy API Payload" to lock the button-component shape (prereq #2).

## Backend design (once prerequisites land)

### 1. Sync - detect the dynamic URL button
`respond_template_service.py`. Raw `components` JSONB already captured (incl. buttons).
Add helpers:
- `_url_button_of(components)` → the BUTTONS component's dynamic-URL sub-button
  (its 0-based `index` within the buttons block + the base URL template, e.g.
  `https://fe-sorento.foundryx.my/{{1}}`).
Compute on the fly from `components` - **no migration / no new column**.

### 2. Defaults - map the button URL var
`set_default` / `serialize_default` / `PARAM_VARIABLES`:
- Reserve a param-mapping key `"button_url"` → a CRM var (default `portal_url`).
- Validation: if template has a dynamic URL button, require `button_url` mapped
  (mirror `REQUIRED_PARAM_VARIABLE` for `portal_otp`). Body slots `1..param_count`
  validated as today (button is separate from positional body count).

### 3. Resolve - full URL → button suffix
`respond_messaging_service.py`:
- `resolve_template_params` stays body-only.
- New: resolve `button_url` var → strip the button's base prefix (everything before
  `{{1}}` in the stored button URL template) from the resolved `portal_url`, leaving
  the dynamic suffix (e.g. `portal/c/.../complaint/<id>`). URL-encode per Meta rules.
- `portal_url` already populated for complaint via `extract_first_url(text)` in
  `send_text_or_template` - keep, or set explicitly in `build_context_vars`.

### 4. Send - emit the button component
`integration_service.py::send_template_message`:
- Add optional `button: dict | None` (button text, base url, suffix).
- When present, append the locked respond.io `buttons` component (see
  "Locked button-component shape" above) after the `body` component.
- Body component unchanged.

### 5. Flatten char (D2)
`sanitize_param(flatten=True)`: `" | "` → `" "`.

### 6. In-window (D1, if decouple)
`send_text_or_template` window-open branch sends rich `text` directly (skip
`render_in_window_text` for button use-cases) - full detail + clickable URL, no button.

## Frontend (admin modal)

`account/.../respond-templates` default-template modal: when the selected template
has a dynamic URL button, render an extra mapping row "Button link → [var]"
(default `portal_url`). Wire through the PUT `/template-defaults/{use_case}` payload.

## Tests (Phase 2)

- **pytest:** `test_respond_templates.py` - button detection in sync; `set_default`
  requires `button_url` when button present; closed-window send emits button
  component with correct suffix; suffix-stripping from full portal URL; flatten char.
- **vitest:** modal renders + submits the button mapping row.
- **playwright:** configure default with button mapping; (send path can't hit live
  WhatsApp - assert the outbox `request_payload` carries the button component).

## Rollout

Per-use-case, fallback-safe: no button mapping configured → behaves exactly as today
(body-only template). Zero behavior change until an admin maps a button template.

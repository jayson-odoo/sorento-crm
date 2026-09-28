# PLAN: one branded email layout for every outgoing mail, theme and element order configurable (#1349)

**Status:** built, reviewed (reviewer + security), browser-verified at 1280/375; waiting on main's two alembic heads to be joined, then one re-parent push, and on the owner's alignment round (Q1 to Q8). Full track.
**Base:** origin/main `445cb1eb37f4e66820f007ca4730c09ee0225128`. `alembic heads` on it: `merge_28sep_batch3 (head)`, one head.
**Lane branch:** `claude/email-layout-theme-h8nb3p` (the session-designated branch; the brief named `feat/email-layout-theme`, the harness only allows pushes to the designated one). One PR against main.
**UAC:** `email-layout-28sep-acceptance-criteria.md` (AC-EM001 onward). **Alignment page:** `ALIGN-email-layout.html`.

## The ask (owner, 28 Sep 20:4x MYT, verbatim)

> "I think it's time for us to beautify our email templates because now our email templates are kind of not very nice. It's not professional. It's not up to the SaaS standard. So I want you to look into the best practice in the email template from SaaS. For example, Respond IO, Figma, even Instagram or anything. And need to refer to their email template and superimpose the style to all our existing email template. For example, like for Respond IO email, there's always a very big button centered so that it attracts people to click on it to open it. So I think our email template need to be nicer. You can refer to the Dreams EMS repository that has a quite good email template style. Okay, and the style is configurable at their site. So the style also need to be configurable at our site also like we can arrange the element, theme, etc."

## Journey

1. An admin opens **System Management > Email Theme**, sets the logo, brand colour, button style, font and footer (company, address, help contact, "why you received this", social links), and watches one sample mail update live at desktop width (600) and phone width (375). Save.
2. The admin opens **System Management > Email Templates > (a template)**, clicks Edit, and sees the mail as an ordered list of blocks: brand header, heading, intro, facts table, CTA button, secondary link, custom text, footer. They move a block up or down (or drag it), add or remove one, change its settings, and see the same preview iframe update. Save.
3. Every mail the system sends (password reset, invitation, procurement, complaints, SLA digest, attachments, onboarding, automations, bare notifications) arrives as the same branded card: soft page background, white 600px card with rounded corners, logo on the brand band, a preheader line in the inbox list, one big centred button where the mail has an action, the facts in a quiet table, a footer with company, address, help and why-you-got-this. The plain-text part carries the same content.
4. A template an admin broke (bad Jinja) still sends: the recipient gets the plain safe layout with the subject and the text, the error is logged, and `[template-error:...]` never reaches an inbox.

## What exists today (verified on 445cb1eb)

- `EmailTemplate` (code, name, subject, body_html, body_text, unused variables_schema). Rendering: `app/services/templating.py` (SandboxedEnvironment, autoescape, `[template-error:...]` on failure), `email_template_service.render`.
- **Six** seeded templates, not the four the issue lists: `purchase_request_approved_default`, `sponsorship_form_approved_default` (212), `order_inquiry_handover_default` (oihe_0001, reshaped by oihr_0001, oihr_0003, soatt_0001), `order_inquiry_undone_default` (undo_0002, oihr_0002), `order_inquiry_reserve_requested_default` (oirs_0001) and `order_inquiry_reserved_default` (oirs_0001, oirs_0003). The last two are extra to the issue's inventory.
- Hand-built f-string mails, as the issue lists them (auth, users, user_service, procurement x4 + approval link, complaints x2, attachment helper x4 coalesced in notification_tasks, SLA digest, supplier notice, onboarding x3, title/body-only notifications).
- Single chokepoint for outbound mail already exists: `email_outbox_service.enqueue` / `enqueue_or_merge`. Every producer ends there, directly or through `notification_tasks._enqueue_email_for_delivery`.
- `system_settings` singleton already carries name, logo, address, website_url, support_email, social_* (six networks). `companies.logo_url` exists and is unused for email.
- Frontend: `system-management/email-templates` (dialog with Tiptap StarterKit body, preview iframe on the detail page). `components/common/OrderableList.tsx` and `@dnd-kit` are already in the tree.

## SaaS research: what the good ones do

Sources: Litmus (bulletproof buttons, preview text guide), Mailchimp email design guide and font guidance, caniemail.com (dark mode, `<style>` support), Campaign Monitor CSS support, Postmark transactional best practices, SpamAssassin's MIME_HTML_ONLY rule, Apple HIG and WCAG 2.2 target sizes, Really Good Emails' password reset and notification galleries (Figma, Instagram captures), respond.io and Figma help centre pages for their reset flows. Honest limit: this session's fetch tool could not load the gallery pages themselves (egress blocked), so brand-specific pixel values below come from the well-known shape of those mails, not from a measured capture; the general rules come from the guides above. The dreamz-ems files could not be read from this session either (GitHub access is scoped to this repository); the issue's own verified summary of dreamz-ems (base.html, schemas, compiler, BrandValues, tenant_branding) is what this plan follows.

The shape respond.io, Figma and Instagram share for a transactional mail: logo at the top, one short heading, two lines of copy, **one big centred button**, the raw link underneath for clients that hide buttons, a quiet grey footer. Nothing else competes with the button.

**Adopted**

| Pattern | Why | Where |
|---|---|---|
| 600px table container, centred, on a soft grey page (`#F3F4F6`) | Tables are the only layout every client (Outlook's Word engine included) renders the same; 600 fits every desktop pane | `app/templates/email/base.html` |
| White card, 12px radius, 1px hairline border | The dreamz-ems look; reads as a "product" mail, not a memo | base.html |
| Logo header on the brand band (or white, configurable) | Every reference mail opens with the logo; recognition before content | layout.html `brand_header` |
| Preheader (hidden inbox preview line) padded with zero-width joiners | Inbox list shows a useful line instead of "Hello," | base.html; `EmailTemplate.preheader` |
| One big centred CTA (16px bold, 16px x 40px padding, >= 48px tall, full-width on phones) | The owner's respond.io example; 44-48px is the Apple / Material tap-target minimum | layout.html `button` |
| Bulletproof button: padded `<td bgcolor>` + `<a>`, no image | Outlook ignores padding on `<a>` but honours the cell | layout.html |
| Raw link under the button ("Or paste this link") | Clients that strip buttons, and the phishing-conscious reset mail the old one tried to be | layout.html `link` |
| Generous whitespace: 40px side padding (20 on phones), 16px body, 24px heading | Mailchimp's 14-16px body guidance; phone readability | layout.html |
| Facts table as label/value rows in a tinted panel | How Figma and respond.io show "what changed" without a spreadsheet | layout.html `facts` |
| Every style inline; `<style>` only for the phone breakpoint | Gmail drops `<style>` it cannot parse; inline always renders | layout.html + `inline_defaults()` for admin HTML |
| System font stacks only (6 choices) | Gmail, Outlook and Yahoo do not load web fonts | `FONT_STACKS` |
| Footer: company, address, help contact, why-you-received-this, social links as text | Trust and support path; a text link survives image blocking | layout.html `footer` |
| Logo `alt` = company name, logo by public URL | Images are blocked by default in Outlook; alt still says who it is | layout.html |
| multipart/alternative with a plain-text part derived from the same blocks | HTML-only mail scores worse (SpamAssassin MIME_HTML_ONLY) and loses screen-reader and watch users | `render_document` |
| Mobile-safe at 375 (card goes edge-to-edge, facts stack, button goes full width) | Most transactional opens are on phones | base.html media query |

**Rejected**

| Pattern | Why not |
|---|---|
| MJML via `mrml` | We ship one fixed shell, about 150 lines of table HTML we own. MJML would add a compiler and a second template language between the admin and the output, and the admin's rich text would still have to pass through `mj-text` raw. Jinja inheritance in our sandbox does the job with no new dependency. (Trigger to revisit: a second, structurally different layout, e.g. multi-column newsletters.) |
| Hero images, background images | Blocked by default in Outlook, slow, and distract from the one action |
| Multi-column sections (dreamz's 50/50, 33/33/33) | Cramped in 600px and unreliable on phones; no mail we send needs two columns |
| Web fonts (Inter in dreamz's `mj-all`) | Silently fall back in Gmail/Outlook/Yahoo; a promise the inbox breaks |
| Social icon images | Blocked by default; text links carry the same thing |
| Tracking pixels, open tracking | Surveillance on a security mail; not asked for |
| Dark-mode styles | Out of scope per the issue; Gmail ignores `prefers-color-scheme`. The layout declares `color-scheme: light` so clients that invert do it consistently |
| Inline CID logo | Out of scope per the issue; logo by public URL |
| Full drag-drop canvas port from dreamz (~100KB TSX) | The smallest editor that gives "arrange the element" is an ordered block list with per-block settings; see Decision D5 |

## Decisions

- **D1 Theme storage: one JSONB column `email_theme` on the existing `system_settings` singleton**, not a new table. Why: the singleton already holds the brand facts the theme defaults from (name, logo, address, support email, six social URLs); the theme is always read and written as one object; "one preference does not need a table" (PRINCIPLES). It has its own endpoint (`GET/PUT /api/v1/system/email-theme`) and is NOT added to the settings dict builders, so the LESSONS "both manual dict builders" trap does not apply. Every field is optional; blank means the default, derived from System Settings, logo falling back to the first active company's `logo_url` (owner: "the style is configurable").
- **D2 Layout: Jinja inheritance (`base.html` <- `layout.html`) in a `SandboxedEnvironment` with a `FileSystemLoader` over `app/templates/email/`.** Blocks render their admin Jinja in the SAME sandbox `templating.py` uses; the layout only places the results. No MJML (see Rejected). Admin rich text gets per-tag inline defaults (`inline_defaults`, authored `style` wins) so Tiptap's bare `<p>`/`<table>` look right in every client with no new dependency.
- **D3 Template storage: two nullable columns on `email_templates`: `preheader` (varchar 255) and `layout_json` (JSONB, the block document).** `layout_json` NULL means the implicit document `[brand_header, custom_text(body_html), footer]`, so every admin-authored template joins the layout with no data migration. When `layout_json` is set, `body_html` mirrors the custom-text blocks' HTML (search and the old list keep working, and a downgrade that drops the columns leaves a sensible body). `body_text`, when set, stays the plain-text part (the OI templates' hand-tuned pipe tables keep theirs); when empty, the text part is derived from the blocks.
- **D4 Hand-built mails become EmailTemplate rows with a code**, seeded by a data migration (insert when the code is absent, never overwrite). The same documents live in `app/services/email_system_templates.py`, which `render_code` falls back to when the row is missing or inactive, so a system mail always has a body. Producers call `EmailTemplateService(db).render_code(code, context)` and pass CONTEXT; they never build HTML. Disabling a mail stays the Email Event Configs kill switch, not the template's active flag (Q4).
- **D5 Element arrangement: an ordered block list, not a drag-drop canvas.** Eight block types, exactly the brief's list: brand header, heading, intro, facts table, CTA button, secondary link, custom text, footer. Each has its settings inline; reorder with up/down buttons or drag (the existing `OrderableList` + `@dnd-kit`); add from a menu; remove. Custom text keeps the Tiptap body, plus an HTML source toggle because the OI tables do not round-trip through StarterKit (no Table extension). Preview: the same iframe, fed by a new draft-preview endpoint, at 600 and 375.
- **D6 Safety net at the chokepoint.** `email_outbox_service.enqueue` / `enqueue_or_merge` wrap any body that does not carry the layout marker in the plain safe layout (title/body-only notifications, anything added later that forgets). One opt-out, `layout=False`, used only by the supplier notice (Q1).
- **D7 Fallback.** Email rendering is strict (a template error raises inside the renderer) and `render_document` catches everything: log at ERROR with the traceback, then send the plain safe layout with the rendered subject (or the subject with its Jinja stripped) and the text (the rendered text part, else whatever blocks still render). Last resort if the theme itself fails: bare HTML with the subject and text. `[template-error:...]` never reaches a mail. The legacy non-strict `render_html`/`render_text` stay for their other callers (WhatsApp text).
- **D8 Permissions: reuse `email_templates.templates.*`.** Theme read and theme preview = `email_templates.templates.view`, theme save = `email_templates.templates.edit`; draft preview = `email_templates.templates.edit` (it renders caller-supplied Jinja, which saving a template has always required; security review B2, 28 Sep). No new slug: the theme is part of the email-templates module and the registry has no better slot (`system.*` has settings for SMTP but the SMTP page lives under User Management). Menu: "Email Theme" beside "Email Templates" in both menu trees, same permission.
- **D9 Supplier notice stays text-only** (the issue allows it), see Q1: it is a bilingual EN/中文 cover note to external suppliers carrying the PDF + xlsx, owner-verified in that form; it goes out through `layout=False`.
- **D11 Credential mails are not editable (security review B1, 28 Sep).** Password reset, user invitation, onboarding intake link and purchase request approval link carry a one-time token in their context. They always render their built-in document (the theme still applies), get no seeded row, and the API refuses their codes. Otherwise anyone with `email_templates.templates.edit` could rewrite the reset mail to ship its token to their own server and take over any account through the public reset route. See Q8.
- **D12 Render budget (security review B2/S1, 28 Sep).** The template sandbox caps `range` at 1000 and checks a deadline on every step, refuses `*`/`**` results beyond 100k items or exponents over 64, caps output at 1M characters, and gives one mail 3 seconds (fallback: 0.1 s per block). A runaway template now costs seconds, not a worker; the mail still goes out via the safe layout. Handlers are sync `def` so rendering runs in the thread pool.
- **D10 Theme and template saves are side-writes.** They touch only their own row; nothing else reads them on a business path except rendering, which falls back to defaults field by field if a stored value no longer validates. A theme save cannot block an order, a PR or a mail.

## Block document (the contract)

```json
{"version": 1, "blocks": [
  {"id": "b1", "type": "brand_header"},
  {"id": "b2", "type": "heading", "text": "Reset your password", "align": "left"},
  {"id": "b3", "type": "intro", "text": "Hi {{ recipient.name }},\n\nParagraphs split on blank lines.", "align": "left"},
  {"id": "b4", "type": "facts", "rows": [{"label": "Customer", "value": "{{ pr.customer }}"}], "hide_empty": true},
  {"id": "b5", "type": "button", "label": "Reset password", "url": "{{ reset_link }}"},
  {"id": "b6", "type": "link", "label": "Or paste this link into your browser:", "url": "{{ reset_link }}"},
  {"id": "b7", "type": "custom_text", "html": "<p>Rich text / HTML with Jinja</p>"},
  {"id": "b8", "type": "footer", "note": "optional per-mail why-you-received-this"}
]}
```

Theme (`GET/PUT /api/v1/system/email-theme`): `{theme: {...stored, nulls allowed}, defaults: {...every field filled}, fonts: [{value,label}]}`. Fields: `logo_url, logo_alignment (left|center), logo_height (20-80), header_style (brand|white), primary_color, accent_color, page_background, button_color, button_text_color, button_radius (0-32), button_width (auto|full), card_radius (0-24), font (system|arial|helvetica|verdana|trebuchet|georgia), company_name, address, help_email, help_url, footer_note, social_links [{label,url}] (max 8)`. Colours `#RRGGBB`; URLs http(s) only.

Preview endpoints: `POST /api/v1/system/email-theme/preview {theme}` -> `{subject, body_html, body_text}` of one sample mail (password reset) under the unsaved theme. `POST /api/v1/email-templates/preview-draft {subject, preheader, layout_json, body_html, body_text, code?, context?}` -> rendered with the catalog's sample context.

## Slices

| # | Slice | Before | After |
|---|---|---|---|
| S1 | Layout + renderer + fallback (`email_layout.py`, `templates/email/*`, strict render) | Bare fragments, `[template-error:...]` in mail | Every render goes through one layout; errors send the safe layout |
| S2 | Schema: `email_templates.preheader`, `email_templates.layout_json`, `system_settings.email_theme` (one migration on `merge_28sep_batch3`) | none | columns exist |
| S3 | Theme API + service (`load_theme`, defaults from System Settings) | none | GET/PUT/preview |
| S4 | EmailTemplate API: preheader + layout_json in CRUD, draft preview, variables per code incl. `handover.*` and `undo.*` | body_html only | block document round trip |
| S5 | Seeded templates onto blocks (data migration, only rows whose body_html sha256 still equals the seeded body) | 6 bare fragments | heading + tables + big button |
| S6 | Hand-built mails onto codes (auth, users, user_service, procurement x5, complaints x2, attachments x4, SLA digest, onboarding x3, generic) + outbox safety net | f-string HTML in Python | `render_code(code, ctx)` |
| S7 | Frontend: Email Theme page (form + live preview 600/375) | none | new page |
| S8 | Frontend: block editor in the template dialog + preview iframe | Tiptap body only | ordered blocks, reorder, add/remove, preview |
| S9 | Tests, browser pass 1280/375, DoD | | |

## Migrations

- `eml_0001_layout_columns` (down_revision `sales_agent_aliases_r7` after re-parenting onto main 5b18b6d0; originally `merge_28sep_batch3`): add `email_templates.preheader varchar(255) NULL`, `email_templates.layout_json jsonb NULL`, `system_settings.email_theme jsonb NULL`. Additive; downgrade drops them.
- `eml_0002_seed_layouts` (down_revision `eml_0001_layout_columns`): (a) for each of the 6 seeded codes, `UPDATE ... SET layout_json, preheader WHERE code = :code AND layout_json IS NULL` only when `sha256(body_html)` equals the fully migrated seeded body (hashes computed on 445cb1eb by replaying 212, oihe_0001, undo_0002, oihr_0001, oihr_0002, oirs_0001, oirs_0003, oihr_0003, soatt_0001); an admin-edited row is left alone and still renders through the implicit layout. `body_html`/`body_text` are NOT touched, so a downgrade (which nulls `layout_json` again) restores the exact prior rendering. (b) insert one row per system code when the code is absent, never overwriting.
- Never touches `alembic_version`. One head.

## Tests (tester-first per slice, red then green)

Backend: theme resolve/validation/API (view vs edit permission); layout parts (header with logo or name, preheader, CTA table, footer fields, 600 container, media query, inline styles on admin HTML, text part); fallback (bad Jinja in subject, block, text part; broken theme; never `[template-error`); element order round trip (PUT layout_json, GET returns the same order; render follows the order); each migrated email renders the layout with its facts; seeded conversion migration (touches only the seeded hash; downgrade); outbox safety net (plain text notification gets the layout; supplier notice opts out). Existing sender tests keep passing or have their pins moved with the reason stated in the PR.
Frontend (vitest): theme page (fields, dropdowns are the system select, save calls PUT, preview requests on change), block editor (add, remove, move up/down, settings edit, payload order), preview iframe at 600/375.
Browser: agent-browser at 1280 and 375 on the theme page, the editor and the preview.

## Open questions (my recommendation in bold)

1. **Q1 Supplier loading notice / container request: keep it text-only in this PR** (bilingual cover note with PDF + xlsx to external suppliers; owner-verified format; `layout=False`). Alternative: branded like the rest. **Recommend keep text-only; brand it in a follow-up if you want suppliers to see the card.**
2. **Q2 Password reset and invitation: big button plus the raw link underneath** (the old reset mail showed only the raw URL "to reduce phishing concern"). **Recommend button + visible link**, which keeps the URL visible and adds the button respond.io uses.
3. **Q3 Footer social links: text links, no icon images.** **Recommend text links** (icons are blocked by default in Outlook).
4. **Q4 A system template set inactive: still send with the built-in default document.** Disabling a mail stays the Email Event Configs kill switch. **Recommend this**, so a template toggle can never silently stop password resets.
5. **Q5 Brand colour default: `#2563EB`** (the app's own primary blue) until you set one. **Recommend this**; the theme page changes it in one field.
6. **Q6 Header style default: logo on the brand-colour band, centred.** Alternative: white header with a hairline. **Recommend the band** (dreamz look, strongest brand recognition); both are one dropdown away.
8. **Q8 Credential mails (reset, invitation, intake link, approval link): wording fixed in code, not editable** (D11). Alternative: editable wording with the token link injected by code outside the admin's Jinja. **Recommend fixed for this PR**; the editable variant is a follow-up if you want to reword them.
7. **Q7 Unknown variables still render as `[unknown:name]`** (existing behaviour, shows the admin a typo in preview). **Recommend keep** for this PR; hiding them in sent mail can be a follow-up if you want it.

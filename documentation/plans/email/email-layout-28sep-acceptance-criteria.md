# UAC: branded email layout, theme and element order (#1349)

Plan: `PLAN-email-layout-28sep.md`. One AC per behaviour. "The layout" means `app/templates/email/layout.html` rendered by `app/services/email_layout.py`.

## Layout parts

- **AC-EM001** Every rendered mail is a full HTML document whose body holds a 100%-wide table on the theme page background, containing a centred 600px table card (white, theme card radius, hairline border).
- **AC-EM002** The brand header block shows the theme logo as an `<img>` with `alt` = company name and the theme logo height, aligned left or centre per theme, on the brand colour band (header style `brand`) or white with a hairline (header style `white`). With no logo it shows the company name as text.
- **AC-EM003** A template with a preheader renders it as the first element in `<body>`, hidden (display none, zero size), followed by zero-width padding. A template without a preheader uses the first intro block's text, cut to 140 characters. No intro and no preheader: no preheader element.
- **AC-EM004** A button block renders one centred bulletproof button (a `<td bgcolor>` holding an `<a>`) in the theme button colour, text colour and radius, 16px bold text with 16px x 40px padding; `button_width: full` makes it 100% wide. A button whose URL renders empty is not rendered.
- **AC-EM005** A link block renders its label and the raw URL as a visible link, centred under the button.
- **AC-EM006** A facts block renders label/value rows in a tinted panel; with `hide_empty` (the default) a row whose value renders empty, `-` or `None` is dropped; a facts block with no rows left is not rendered.
- **AC-EM007** The footer block renders the theme company name, address, help link and/or help email, social links as text links, and the "why you received this" line; a footer block `note` replaces the theme's line for that mail.
- **AC-EM008** Every layout element carries its styles inline. Admin-authored HTML in custom text blocks gets per-tag inline defaults (p, h1-h3, ul, ol, li, blockquote, table, th, td, hr, a); an authored `style` attribute keeps its declarations and wins over the default.
- **AC-EM009** The document carries a `@media (max-width: 620px)` rule that makes the card full width, reduces side padding to 20px, stacks facts rows and makes the button full width; the mail reads without horizontal scroll at 375px (browser-verified screenshot).
- **AC-EM010** The plain-text part is derived from the same rendered blocks in order (heading, intro, facts as `Label: value`, button as `Label: url`, custom text via html2text, footer lines); the secondary link is omitted from text when it repeats the button URL. A template with its own `body_text` uses that instead.
- **AC-EM011** Button and link URLs that are not http(s), mailto or site-relative (e.g. `javascript:`) are dropped. The body carries the `data-sorento-layout` marker.

## Theme

- **AC-EM020** `GET /api/v1/system/email-theme` (permission `email_templates.templates.view`) returns `{theme, defaults, fonts}`: the stored overrides (nulls allowed), every field's effective default, and the six font choices.
- **AC-EM021** `PUT /api/v1/system/email-theme` (permission `email_templates.templates.edit`) stores the theme in `system_settings.email_theme`; invalid values (colour not `#RRGGBB`, radius out of range, unknown font or alignment, non-http logo/help URL, a social link that is not http(s)/mailto, more than 8 socials) return 422 and store nothing.
- **AC-EM022** Unset theme fields default from System Settings: company name from `name`, logo from `logo` else the first active company's `logo_url`, address, help email from `support_email`, help URL from `website_url`, social links from the six `social_*` fields; colours default to `#2563EB` on `#F3F4F6`, button colour follows the primary colour.
- **AC-EM023** A stored theme value that no longer validates is ignored at render time for that field only (logged), never failing the mail.
- **AC-EM024** Saving the theme writes only `system_settings.email_theme`; other System Settings fields are unchanged.

## Live preview

- **AC-EM030** The Email Theme page previews one sample mail (password reset) rendered by the backend under the UNSAVED form values, in an iframe at 600px (desktop) and 375px (mobile), refreshing as fields change.
- **AC-EM031** The template editor previews the unsaved draft (subject, preheader, blocks) through `POST /api/v1/email-templates/preview-draft` in the same iframe, with a desktop 600 / mobile 375 toggle, using the catalog sample context.

## Element order editor

- **AC-EM040** The template editor lists the template's blocks in order; a template with no `layout_json` shows the implicit list brand header, custom text (its current body), footer.
- **AC-EM041** Each block can move up or down with buttons, or be dragged; the first cannot move up, the last cannot move down.
- **AC-EM042** A block of any of the eight types (brand header, heading, intro, facts table, CTA button, secondary link, custom text, footer) can be added from a menu, and any block can be removed.
- **AC-EM043** Each block exposes its own settings: heading text and alignment; intro text and alignment; facts rows (label, value, add/remove row) and hide-empty; button label and URL; link label and URL; custom text (rich text with an HTML source toggle); footer note.
- **AC-EM044** Saving sends `layout_json` with the blocks in the on-screen order; `GET` returns the same order; rendering follows that order.
- **AC-EM045** The custom text block edits with the existing Tiptap editor; its HTML source toggle edits the raw HTML (tables survive); `body_html` mirrors the custom text blocks on save.
- **AC-EM046** The variables catalog includes `handover.*` (headline, subject_scope, orders, lines, link) and `undo.*` (headline, so_number, revision_no, customer, project, lines, link), plus each system template's own variables when the template has a system code.

## Every email on the layout (by name)

Seeded automation templates (converted by `eml_0002_seed_layouts`, only while their body is still the seeded one):
- **AC-EM050** Purchase request approved (`purchase_request_approved_default`): heading, greeting intro, facts (customer, project, purpose, requested by, approved by, approved at, expected delivery, expected PO date), approval comments, "Open purchase request" button.
- **AC-EM051** Sponsorship form approved (`sponsorship_form_approved_default`): same shape with total project value, "Open sponsorship form" button.
- **AC-EM052** Order inquiry handover (`order_inquiry_handover_default`): headline as heading, SO table and line table (CHANGE TO columns only when used, attachments in remark), raised-by line, "Open in Order Inquiries" button; its hand-tuned text part unchanged.
- **AC-EM053** Order inquiry undone (`order_inquiry_undone_default`): headline heading, customer/project, line table, undone-by line, button.
- **AC-EM054** Reserve requested (`order_inquiry_reserve_requested_default`) and **AC-EM055** Stock reserved (`order_inquiry_reserved_default`): heading, intro sentence, table, note/open-rows line, button.

Hand-built mails (now `render_code(code, ctx)`, producers pass context):
- **AC-EM060** Password reset (`auth_password_reset`): heading, intro, "Reset password" button, raw link, ignore-if-not-you line.
- **AC-EM061** User invitation (`user_invitation`): heading, intro, "Set your password" button, raw link.
- **AC-EM062** Sign-in email updated (`account_email_changed`): facts previous/new, "Sign in" button.
- **AC-EM063** Stock inquiry created (`stock_inquiry_created`).
- **AC-EM064** Purchase request / sponsorship created or updated notice (`purchase_request_submitted`).
- **AC-EM065** Requester notified approved (`purchase_request_requester_approved`) and **AC-EM066** rejected (`purchase_request_requester_rejected`).
- **AC-EM067** Approval link (`purchase_request_approval_link`): big "Review and approve" button.
- **AC-EM068** Complaint created / resubmitted (`complaint_created`) and **AC-EM069** replacement DO delivered (`complaint_do_delivered`).
- **AC-EM070** External attachment linked notice, coalesced (`attachment_linked`): the merged list of every attachment in the window, re-rendered on merge.
- **AC-EM071** Promotion created notice (`promotion_created`).
- **AC-EM072** Daily SLA summary (`sla_daily_summary`): facts (outstanding, 7-day, 30-day), conversations table, "Open my SLA tracking" button, unsubscribe link.
- **AC-EM073** Onboarding intake link (`onboarding_intake_link`), **AC-EM074** onboarding submitted (`onboarding_submitted`), **AC-EM075** onboarding complete (`onboarding_completed`).
- **AC-EM076** Any notification with only a title and body (NotificationService, external/*): the layout with the title as heading and the body as intro, plus a button when the notification carries a link.
- **AC-EM077** Supplier loading notice and container request stay text-only (`layout=False`), unchanged.

## Fallback

- **AC-EM080** A template whose block, subject or text part raises during rendering still produces a mail: the plain safe layout (brand header, text as paragraphs, footer) with the subject; the error is logged at ERROR; no `[template-error` string appears in subject, HTML or text.
- **AC-EM081** A subject that fails to render falls back to the subject source with its Jinja tags removed (or "Notification" if nothing is left).
- **AC-EM082** A theme that cannot render yields a bare HTML mail with the subject and text; still no error marker.
- **AC-EM083** An automation run whose template is broken still enqueues its mails (safe layout) and the run is `success`.
- **AC-EM085** `email_outbox_service.enqueue` / `enqueue_or_merge` wrap any HTML or text body that lacks the layout marker in the safe layout before writing the outbox row.

## Permissions and navigation

- **AC-EM090** Theme GET and both preview endpoints need `email_templates.templates.view`; theme PUT needs `email_templates.templates.edit`; a user without them gets 403.
- **AC-EM092** The four credential mails (`auth_password_reset`, `user_invitation`, `onboarding_intake_link`, `purchase_request_approval_link`) always render their built-in document; an `email_templates` row with one of those codes is ignored, and creating or renaming a template to one of them returns 422 (security review B1).
- **AC-EM093** A template that loops or allocates without bound (nested `range`, huge `*`/`**`) stops within seconds and the mail still sends via the safe layout; draft preview requires `email_templates.templates.edit` and rejects bodies over 200k characters and contexts over 100k (security review B2/S1/S2).
- **AC-EM091** "Email Theme" appears in System Management next to "Email Templates" in both menu trees, gated by `email_templates.templates.view`; the page has one primary CTA (Save), no subtitle, and every select is the system dropdown component.

## Migrations

- **AC-EM095** `eml_0002_seed_layouts` sets `layout_json` + `preheader` on a seeded template only when its `body_html` sha256 equals the seeded body and `layout_json` is NULL; an admin-edited row is untouched; `body_html`/`body_text` are never modified; downgrade nulls what it set.
- **AC-EM096** The same migration inserts one `email_templates` row per system code when that code is absent and never overwrites an existing row.
- **AC-EM097** One alembic head after the lane's migrations; the first one chains on `merge_28sep_batch3`.

# PLAN: customer sign page shows the quotation's own columns (QUOTE-SIGN-COLUMNS)

Status: in progress (small fix track: one shared column definition, no migration, no auth change)

## Journey

The customer opens the counter-sign link and reads the quotation they are being asked to sign.
Owner, 2 Nov: the page has no product photo column, while the quotation (PDF and CRM) does.
Rulings: CRM forms = portal forms (28 Oct); email = preview = attachment tally (28 Oct).

## Rule

The public sign page shows the SAME columns, in the same order, with the same labels as the
quotation PDF, product photo and drawing (technical spec) included, driven by ONE column
definition on the backend. Mobile may stack, never drop.

## Plan

1. Backend: one `quotation_columns(lines)` in the PDF service decides the column set (photo
   only when a line on the scope has one, the rest always). The PDF renders from it; the sign
   page serializer returns it per scope as `columns: [{key, label}]`.
2. Sign page lines carry `image_url` / `drawing_url`: an inline downscaled data URI from
   `product_image_service.data_uri`, the same bytes the PDF embeds. No storage key, no signed
   URL to a private bucket, nothing that needs a login.
3. Frontend `QuotationSignScopes` renders headers and cells from `scope.columns` instead of a
   hand-kept list (one cell renderer per key).
4. Tests red first: backend asserts sign-page column labels == PDF column labels for a scope
   with photos, and that photos are data URIs; vitest asserts the photo column renders.

See `quote-sign-columns-2nov-acceptance-criteria.md`.

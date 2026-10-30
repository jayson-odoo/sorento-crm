# PLAN: product file link / unlink audit + delete permission (PRODUCT-ATTACH-AUDIT)

Status: in progress (small fix track: backend only, no migration; permission change, so the
security reviewer joins)

## Why

Owner, 28 Oct 2026: the SRTUB6503 drawing link (a `product_attachments` row) disappeared between
11:48 and 12:07 and nobody can say who. `ProductAttachment` (`app/models/product.py:497`) and
`CertificateProduct` (`app/models/certificate.py:279`) carry `__audit_skip__` (review B3 volume
decision), so a link or unlink leaves no trace. And `DELETE /master-data/product-attachments/{id}`
(`app/api/v1/master_data/product_attachments.py:300`) checks only that the caller is signed in.

## Measured facts (origin/main 549a6842)

- Create (`:236`), update (`:281`) and delete (`:300`) all take `get_current_user` only. The brief
  said create/update need `master_data.product_attachments.edit`; they do not. The slug exists
  (`app/rbac/permission_registry.py:213`) and the brochure-image routes (`:83`, `:108`, `:131`)
  already require it.
- Staff-driven link writes: the master-data POST/DELETE above, certificate coverage add/remove
  (`app/api/v1/master_data/certificates.py` `POST/DELETE /{id}/products`, already gated on the
  certificate edit slug), and the catalogue photo attach (`catalogue_photo_service.attach`, a
  staff click that can replace a lookalike photo, i.e. unlink one).
- Integration / sync writes, left unaudited (B3): the external n8n link routes
  (`app/api/v1/external/product_attachments.py`), certificate `reconcile`, company twin copy
  (`attachment_company_service.py`), set fan-out. These are the bulk of the 259 to 4,399 rows a
  day; the staff screens are a handful a day.

## Do

1. POST, PUT and DELETE `/master-data/product-attachments` require
   `master_data.product_attachments.edit` (red-first: a signed-in user without it gets 403).
   Owner ruling 28 Oct (crew answer (b)): gate all three alike; the external / integration link
   routes keep their own auth. Before merge, the roles holding the slug are compared with the
   people who linked files recently (read-only SQL posted on the PR).
2. One explicit audit row per staff link / unlink (`log_audit`, no listener change, the
   `__audit_skip__` stays): action `LINK` / `UNLINK`, `root_entity_type="product"`, root id = the
   product, old/new values = attachment id, filename, attachment type (+ certificate number for
   coverage), description `File linked: <filename> (<type>)` / `File unlinked: <filename> (<type>)`.
   The product Audit Trail (`components/audit/AuditTrail.tsx:47`) prints the description of a
   non-UPDATE row as is, so no frontend change.
3. Written from: master-data POST/DELETE, certificate coverage POST/DELETE routes, catalogue photo
   attach (link + replace unlink). Not from the external / reconcile / twin / set paths.

## Tests

`tests/test_product_attachment_audit.py`: 403 on POST, PUT and DELETE without the slug; a
non-admin holding it can delete; delete writes one UNLINK row rooted on the product with filename
+ type; create writes LINK, a re-POST writes none; certificate coverage add/remove writes
LINK/UNLINK, covering a second product does not re-log the first; unlinking a cert file from the
product writes one row; the n8n intake writes none; the product trail endpoint returns the row
with the description; the Activity timeline reads it as added/removed with no id chips (LINK /
UNLINK map to created / deleted in `activity_service._fe_action`). Catalogue photo replace:
`tests/test_catalogue_photo_readings_api.py`.

# PLAN: contact delete fails on foreign keys (CONTACT-DELETE-FK)

Status: in progress (Build). Small fix track: bug, expected diff well under 300 lines, no auth/RBAC change.

## Report

Contacts > select one > Delete contacts fails. The toast shows raw psycopg text:
`ForeignKeyViolation ... price_tag_requests_contact_id_fkey ... [SQL: DELETE FROM respond_contacts ...]`.

## Bugs

- A. Contact delete crashes whenever a record without `ON DELETE` still references the contact.
- B. Raw SQLAlchemy / psycopg text reaches the toast through `handle_internal_error(str(e))`.

## Approach

Filled in as the FK inventory lands (see below).

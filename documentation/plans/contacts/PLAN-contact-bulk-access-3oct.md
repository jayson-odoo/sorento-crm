# PLAN: Contact bulk access copy + access list filters (CONTACT-BULK-ACCESS)

Status: Plan - card + mock v1 filed, waiting on owner answers Q1-Q5 and crew's masked dev rows; UAC drafted on
the recommended answers. Track: M (LEAD pattern), no migration, no new permission slug.

Card: `CARD-contact-bulk-access-3oct.md`. UAC: `contact-bulk-access-3oct-acceptance-criteria.md`.
Mock: `documentation/mockups/CONTACT-BULK-ACCESS/index.html` (v1, on hold).

## Slices

S1 Backend copy service + endpoint (A1)
- New `app/services/contact_access_copy_service.py`: `snapshot(db, contact_id) -> AccessSnapshot`,
  `diff(source, target) -> list[Change]`, `copy_access(db, source_id, target_ids, dry_run, actor_id)`.
  The access set is one tuple of facets, each a (read, write) pair; ACCESS-MODEL swaps the reveals and
  agents entries for roles and overrides (card 3c). Per-target `begin_nested()` savepoint, commit at the end
  of the route (`get_db` never commits).
- Writes reuse existing writers: `contact_field_reveal_service.set_granted_keys`, the access-types
  relationship, the switch columns, `ContactService.write_chatbot_profile_keeping_facts` for tier, direct
  `ContactAgentAccess` upsert/delete (match by contact id, then by phone for legacy rows).
- Route in `app/api/v1/user_management/contacts.py`, declared before `/{contact_id}` routes, guarded by
  `require_permission("user_management.contacts.edit")`.

S2 Backend list columns + filters (A2)
- `ContactService.list_contacts` grows the filters; `contact_to_response_dict` path adds `chatbot_tier` and a
  batched `cost_visible`; schema `RespondContactResponse` declares both (response_model drops undeclared).
- `access_differs_from` reuses S1's snapshot + diff over the candidate set (contacts table is ~250 rows; one
  batched snapshot query per facet, not per row).

S3 Frontend (A2.2-A2.3, A3)
- `contacts/lib/listQuery.ts` filters, `ContactAccessFilters.tsx`, columns in `ContactsList.tsx`,
  `BulkCopyAccessDialog.tsx` replacing `BulkCopySettingsFromContactDialog.tsx`, service + hook.

## Test list (red first)

Backend `tests/test_contact_bulk_copy_access.py` (Postgres, `blank_session`, HTTP through TestClient):
1. dry_run writes nothing; returns change rows (A1.1, A1.2, A1.10)
2. apply makes target equal to source on every facet, replace semantics removes extra reveal + agent (A1.3)
3. customers / memory / name untouched; source untouched (A1.4)
4. identical target -> unchanged, no write (A1.5)
5. source among targets -> skipped (A1.6)
6. unknown target -> failed, others applied (A1.7)
7. one target's write raises (monkeypatch) -> failed, its access unchanged, others applied (A1.8)
8. unknown source 404; 501 targets 422 (A1.9)
9. no edit permission 403 (A1.11)
10. legacy phone-only agent row -> no duplicate (A1.12)
11. preview == apply change rows (A1.13)

Backend `tests/test_contacts_access_filters.py`:
12. row carries chatbot_tier + cost_visible (A2.1)
13. each filter alone, and two combined (A2.3, A2.4)
14. access_differs_from == contacts a copy would change, excludes X (A2.5)
15. customer_id respects company scope (A2.6)

Frontend vitest:
16. listQuery filters round-trip URL (A2.3)
17. BulkCopyAccessDialog: preview renders counts and red/green rows; apply shows result table; HTTP error ends on
    the message, not a spinner (A3.2-A3.4)

Kill tests (reviewer): mutate replace -> add-only, drop the per-target savepoint, drop the scope predicate; each
must turn a test red.

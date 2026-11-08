# PLAN - TAG-UNION: contact tags add up

Status: PR ready for owner review (built red-first; reviewer + security review fixed; cloud browser pass done; prod recompute script pending owner run). Track: full (migration, RBAC gate change, prod data recompute). Lane TAG-UNION, PR #2254.
Card: `CARD-tag-union-08nov.md` (rule table, owner answers). UAC: `tag-union-08nov-acceptance-criteria.md`.

## Decisions (owner, 8 Nov ~16:00)

- D1 (Q1a) A tag that does not set a setting is neutral.
- D2 (Q2b) Everything adds up. Grants: union / any tag on = on, AI replies and every chatbot switch included.
  Restrictions (hidden / excluded lists, "hide empty locations", "requires registered project"): only when every
  tag that sets them says so. Limits, memory level: max. Stock mode: loosest. Tier and AI model are not switches:
  unchanged rules.
- D3 (Q3a) Existing values that differ from today's tag result are kept as the contact's own changes and listed in
  the dry run; "Apply settings" on the contact resets them.
- D4 (Q4a) Adding or removing a tag, and switching a tag active / inactive, needs the gate of every gated section
  the tag sets (companies = superadmin, stock = inventory.stock.edit, agents = access_agents.edit, messaging =
  respond_workspaces.edit), on top of contacts.edit. The WhatsApp agent path goes through the same service.
- D5 (Q5) "Apply settings" keeps its name; its action is "reset this contact (these contacts) to their tags".
- Out of scope: per-tag brand/class pairing (known limit in the card).

## Design

1. Merge (`contact_tag_settings._merge_kind`): new kinds per the card's table. Include list on one tag and exclude
   list on another (stock, specs) resolves to the exclude list `E minus I` (no conflict).
2. Inactive tags: `tags_by_contact_with_settings` returns active tags only (merge, Differs count, AI model, dealer
   check). The legacy seeding reads every tag (that is what the old apply did).
3. Own changes: new column `respond_contacts.tag_settings_snapshot` JSONB, `{"<section>|<key>": {"v": value the
   tags last wrote, "base": value before tags took the setting over (absent = unknown)}}`. NULL = never seeded.
4. Recompute (`contact_tag_union.recompute(db, contact_ids, keys)`), per setting:
   - X = tag union (for the pivot lists companies / access types / segments / attachment types: union plus `base`,
     so what the contact held before the tags is kept underneath them).
   - not in snapshot (tags take the setting over): base = current, target = X.
   - in snapshot, lists: target = (X + (current - v)) - (v - current) (own adds and removals survive).
   - in snapshot, other values (or an "All" on either side): target = X if current == v else current.
   - in snapshot but no active tag sets it any more: X = base, same rule; entry dropped. Unknown base: value stays.
   - conflicts (tier dealer + end user), the AI model (read live) and blocked portal forms are skipped.
   Writes go through the existing `contact_tag_apply._WRITERS`, one audit row per changed contact.
5. Triggers (live): `set_contact_tags`, `bulk_tag` (UI + WhatsApp agent), `update_tag` (settings or is_active),
   `delete_tag`. Each seeds first (5), then changes, then recomputes only the settings the changed tags set (so a
   recompute never writes a section the gate did not check). Same transaction as the change.
6. Seeding (`ensure_seeded`): for a contact whose snapshot is NULL, per setting its tags set, `v` = TODAY's rule
   (intersect / AND, inactive tags included); for the pivot lists `base` = current minus v. Old-rule conflicts get
   no entry (the union decides them). Run before every live change and by the script.
7. "Apply settings" (`contact_tag_apply.apply_settings`): unchanged preview and per-section rights; on write it also
   sets the snapshot entry to the written value (own change dropped).
8. Script `sorento_crm_backend/scripts/recompute_contact_tag_union.py`: `--dry-run` (default) prints the summary
   (contacts changed, by setting, widened / narrowed, empty-companies today, own changes kept, old conflicts now
   decided, contacts on inactive tags only); `--apply --expect N` refuses unless N equals the changed count; one
   savepoint per contact. Seeds every tagged contact.
9. UI: contact Tag settings section says "Own change" where it said "Differs"; nothing else moves.

Trigger named, not built: if a tag edit with many holders proves slow on prod, the recompute moves to the worker.

## Tests (red first)

`tests/test_contact_tags_union.py`: merge per card row (incl. Sorento + Mocha disjoint companies, include + exclude
resolution, AI replies OR, restriction AND), inactive tag ignored (merge, AI model, dealer), live recompute on add /
remove / settings edit / deactivate / delete, own add / own removal / own scalar survive, untouched scalar reverts to
base, seeding keeps a differing value as own, Apply settings resets own changes, D4 gate 403 (PUT, bulk, toggle),
script dry run counts + `--expect` refusal. Old S2/S3 tests that pin the old merge rules are updated to the new
rules (named in the PR).

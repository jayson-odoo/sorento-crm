# PLAN: agent bulk wave 2, contact tags from a pasted table (AGENT-BULK-W2-TAGS)

Status: Plan, behaviour card posted to crew (crew-ask on #2247); building the parts the questions do not block.
Track: full (agent write path; no migration, no new permission, no new ingest surface).

Wave 2 after AGENT-BULK-V2 (#2241). Owner wave order (8 Nov): 2 contact tags (this lane), 3 sales agent ->
customers, 4 contact edits keyed by phone, 5 product fields, 6 supplier fields.

## Step 1: the tag engine today (main @ c358eb69, file:line)

Paths are under `sorento_crm_backend/app/`.

1. **Catalog.** `models/access.py:118` `ContactTag` (name unique by `lower(name)`, `is_active`, `settings` JSONB =
   the access a tag carries); `models/access.py:142` `respond_contact_tags` (contact_id, tag_id, created_by). Contacts
   are global (no company column on the tag).
2. **Screen add / remove.** `POST /contacts/bulk-tags` (`api/v1/user_management/contact_tags.py:157`), slug
   `user_management.contacts.edit` (`contact_tags.py:45`), -> `ContactTagService.bulk_tag`
   (`services/contact_tag_service.py:227`): per contact `tags_before` / `tags_after`, only the differing
   memberships written, one `log_audit` row per contact per tag ("Tag added: X" / "Tag removed: X",
   `contact_tag_service.py:193`).
3. **Tags are access.** Add mode on the screen defaults to "Apply tag settings now"
   (`sorento_crm_frontend/app/(protected)/user-management/contacts/components/BulkTagDialog.tsx:132`,
   `applySettings: applyNow`): `bulk_tag(apply_settings=True, gates=_gates(...))` writes the membership, then
   `contact_tag_apply.apply_settings(only_tags=added)` inside one savepoint, a dry run rolls the savepoint back
   (`contact_tag_service.py:296-320`). Remove never reverts settings (screen and service).
4. **The preview / not-applied engine.** `services/contact_tag_apply.py:371` `apply_settings`: per contact
   `changes` (before / after, decided_by), `conflicts` (two tags disagree: never written), `not_applied`
   (a section the actor may not write, `_can_write` `contact_tag_apply.py:36`: the section's own gate slug from
   `contact_tag_settings._GATES`, superadmin-only sections, else `user_management.contacts.edit`; held-back
   stock / spec groups), each contact in its own savepoint, audit `_audit` (`contact_tag_apply.py:465`). Sections
   the actor cannot READ are redacted (`contact_tag_settings.unreadable_sections`, `contact_tag_settings.py:1013`).
5. **Gates.** `_gates(db, user)` (`contact_tags.py:32`) = (`UserPermissionService.check_user_has_permission`,
   `_is_superadmin`).

## Step 1: the #2241 path this wave reuses

`chatbot/agent/batch.py` (`crm_batch_propose`, any `WriteDef(batchable=True)`; `propose_rows` -> steps / skipped /
waiting; `preview_block` Ready / Needs your choice / Not changed; `_not_listed` = a picked code must be one the last
table listed or the user typed), `chatbot/agent/writes.py:35` `WriteDef` + `propose_step` (`writes.py:551`),
`chatbot/agent/actions.py` (Confirm card, per-row transaction + recheck of `before`), `chatbot/agent/loop.py`
(`_batch_reply`, `batch_waiting` kept on the turn for the next pick, `loop.py:1952`).

Grant-specific bits in the shared code that a second batchable write must generalise (no new machinery):
- `batch.CHOICE_TAIL` says "account code(s)" and the waiting table's last column is "Account"
  (`batch.py:25`, `batch.py:267`); the tool description talks about customers. Tags need "tag".
- `_not_listed` reads `customer_codes` only (`batch.py:84`). Tag picks travel in `tags_add` / `tags_remove`.
- `loop._not_found_backed` backs only "No customer ..." skip reasons (`loop.py:594`); tags add "No tag named".

## Behaviour card (one write, `crm_contact_tags`, batchable)

A row = one contact + the tags to add and / or remove. Slug `user_management.contacts.edit` (same as the screen).

- **Contact**: by phone only, the #2241 `_find_contact` (both stored forms; two holders = row not changed; none =
  "No contact with this phone"; a tag row never creates a contact).
- **Tag**: exact name (case and spaces aside), active only. Not exact -> the row WAITS with the active tags whose
  name contains the written text (max 10, by name), picked by chat reply; nothing is auto-picked, even one. No tag
  contains it -> "No tag named X" (Not changed). Inactive -> "Tag X is inactive".
- **Add** = the screen's default: membership + that tag's settings applied (`apply_settings(only_tags=added)`), the
  row's "Will change" lists the tag and the settings that change, with "not applied (needs more access): ..." per
  `not_applied`, conflicts listed and never written. **Remove** = membership only (settings stay, as on screen).
- Nothing to change (already holds every tag to add, holds none to remove, no setting differs) -> Not changed
  "Already tagged; nothing to change."
- Confirm: per-row transaction, recheck `before` (tags held + settings before), audit = the screen's rows
  ("Tag added: X" per tag + the tag-settings audit) plus `contact.tags_agent` naming the agent table.

Examples (shapes; real masked rows requested from crew, crew-data-request on #2247):

| # | Pasted row | Result |
|---|---|---|
| E1 | `012-345 6789 / Dealer H / VIP` (tag "VIP" exists, contact holds none) | Ready: add VIP + VIP's settings (e.g. stock check on) |
| E2 | `+60 11-2222 3333 / Hanlim / Johor` (tags "Johor Dealer", "Johor Project") | Needs your choice: row 2 lists both; reply "row 2: Johor Dealer" |
| E3 | `0198887777 / remove Mocha Retail` (contact holds it) | Ready: remove Mocha Retail (settings stay) |
| E4 | `0123334444 / VIP` (already holds VIP, settings match) | Not changed: Already tagged; nothing to change |
| E5 | `0175556666 / Gold` (no tag contains "Gold") | Not changed: No tag named "Gold" |

Questions (each with a recommendation; the build follows the recommendation until answered):
- Q1 Add applies the tag's settings now, as the screen's default? (a) yes, preview lists the setting changes and
  what is not applied (rec, same result as the screen); (b) tag only, settings left for the tag screen's Apply.
- Q2 A tag that does not exist: (a) Not changed "No tag named X" (rec: tags are access groups, created on the tag
  screen with their settings); (b) the agent creates it.
- Q3 A row with a name but no phone: (a) Not changed "Give the phone" (rec: explicit keys only); (b) list contacts
  whose name contains it to pick from.

## UAC

See `agent-bulk-w2-tags-8nov-acceptance-criteria.md`.

# PLAN: Agent field access as a multi-select without duplicates (AGENT-FIELD-MULTI)

Status: Review (S, small fix track: no migration, no auth/RBAC change, no new ingest). Mock v1 approved by owner 20 Oct with option (a) Allow + Deny. PR #1790: red 6e410a7916, fix 0edf8b53bd; hand test filed (laneboard/scripts/1790.md).

UAC: `agent-field-multi-20oct-acceptance-criteria.md` (alongside).

## Owner's words (20 Oct ~00:25 MYT)

"the agent field access need to make it multi select component instead, otherwise will have 2 eta field
which I don't know how to delete"

## What is there today (measured)

- Screen: contact tag detail, Access settings card, group "Agent field access"
  (`sorento_crm_frontend/app/(protected)/user-management/contact-tags/components/ContactTagSettings.tsx:62`).
  Body `AgentFields` (`ContactTagSettings.tsx:567`): one `BoolRow` per entry (Not set / Allow / Deny) plus a
  "Gated field" `SearchableSelect` and an "Add field" button.
- Storage: `contact_tags.settings.agent_fields = [{agent_code, resource, field_key, is_allowed}]`.
- How the duplicate gets in: "Add field" appends the picked field with no check
  (`ContactTagSettings.tsx:612-620`), and the picker still offers fields already listed (`gated`,
  `ContactTagSettings.tsx:574`). The backend validator checks shape, agent and gated-ness but not repeats
  (`sorento_crm_backend/app/services/contact_tag_settings.py:306-328`), so the save stores both.
- Why it cannot be removed: the only remove is choosing "Not set" on the row's toggle in Edit
  (`ContactTagSettings.tsx:592-596`); there is no x, and both duplicate rows share one React key.
- Labels are raw keys (`ContactTagSettings.tsx:576`, `:585`; backend preview label `contact_tag_settings.py:681-683`)
  although readable ones exist in `app/services/field_access.py:127` (`FIELD_LABELS`, `field_label()`).
- Allow and Deny both matter: a tag entry becomes a per-contact `agent_field_access` row, which wins over the
  agent-wide default in either direction (`field_access.py:365-405`). Four fields default to allowed
  (`DEFAULT_ALLOWED`, `field_access.py:117`, plus `eta_delay_date` on the dev DB), so Deny on a tag is how a
  tag hides the ETA from its contacts.
- Dev data (read-only scan of all 18 local `sorento_*` DBs with `contact_tags`, 20 Oct): 0 tags carry a
  duplicate; 1 tag (Dealer) carries agent_fields, one entry (estimated_arrival_date, Allow). The owner's
  4-row screenshot is from a DB not present locally (UNVERIFIED which).

## Change

1. Frontend `AgentFields`: two `SearchableMultiSelect`s through the existing `PickList`, labelled "Allow" and
   "Deny" (the same two-list shape Stock visibility uses: "Only these locations" / "Except these locations",
   `ContactTagSettings.tsx:494-528`). Options = the catalog's gated fields, label
   "<agent name>: <readable field label>". A field picked in one list leaves the other's options. Chips carry
   an x to remove. View: the two lists as pills, each shown only when non-empty. "Set on this tag" stays as is.
2. Collapse duplicates: the stored list is read through one helper keyed on (agent_code, resource, field_key);
   Deny wins, because the server ANDs one tag's entries for a field (`contact_tag_settings.py` `evaluate`
   groups leaves by key, `_m_and`). View, Edit and `cleaned()` on Save all go through it, so an old tag with a
   duplicate shows it once and saves it once. A stored field the catalog no longer offers shows as
   "<agent>: Removed field" with an x; the group body waits for the catalog so nothing flashes as removed.
3. Backend: `_v_agent_fields` rejects a key listed twice (422, "listed twice"); the catalog's `agent_fields`
   options carry `label` from `field_label()`; the preview label at `contact_tag_settings.py:683` uses it too.

No migration: no stored duplicates exist locally; any elsewhere collapse the next time the tag is saved.

## Tests (red first)

- vitest `ContactTagSettings.test.tsx`: multi-select renders existing values as chips with readable labels;
  the x removes a field and Save sends it gone; a stored duplicate renders once and Save sends one entry;
  a field picked under Allow is not offered under Deny.
- pytest `tests/test_contact_tag_settings*.py`: a settings PUT with the same key twice is a 422; the catalog
  options carry readable labels.

## Known edges (reviewer round 1, accepted)

- A tag that still holds a legacy duplicate collapses on its next save, which counts as an agent_fields change:
  a user without `user_management.access_agents.edit` gets the section's 403 when saving another group on that
  tag. No such tag exists locally (scan above).
- The tag list's Settings count (`lib/settingsCount.ts`) counts a legacy duplicate twice until the tag is saved.

## Out of scope

The agent's own "Fields this agent may reveal" card (`access-agents/components/AgentFieldAccessCard.tsx`) is
already a multi-select and is untouched.

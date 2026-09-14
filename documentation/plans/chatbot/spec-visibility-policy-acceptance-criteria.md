# UAC: spec visibility policy (which product spec keys a contact may see)

Plan: `PLAN-spec-visibility-policy.md` (alongside).

## Journey

A CS admin (holding `user_management.contacts.edit`) opens a contact from User Management >
Contacts. Under the Stock visibility card there is a Spec visibility card of the same shape:
a badge saying where today's rule comes from (Contact override / Market segment: Retail /
Default), a rule toggle Show only / Hide these, and one searchable multi-select of product
spec keys by label. The card also prints the net effect, "Hidden today: Thickness, Drainer
board / countertop thickness". The admin ticks the keys and saves; that writes a row for
this contact. Remove drops the row and the card falls back to what the contact inherits.

The same card sits on each market segment (User Management > Market segments) and in
Settings as the global default. Resolution copies stock visibility: a contact override wins
whole; otherwise the contact's market segments are merged most-restrictive (intersection of
Show-only lists, union of Hide lists); otherwise the global default. The default ships
closed: every key visible except `thickness` and `board_thickness`; the Project segment ships
with an empty Hide list (sees everything); Retail and untagged contacts inherit the default.

On the customer side the chatbot's product answers omit hidden keys from the "Specs:" line and
from per-key answers. A direct ask for a hidden key gets "<label>: not available", never "not
recorded". Spec-based product matching ("sinks with 0.8mm bowl") does not match on a hidden
key either, so the value cannot leak through the match. Dealer kit, price tags, the customer
portal and the staff UI are untouched.

## Phase 1 (FE, mocked)

- **AC-1 [FE service]** `services/specVisibilityService.ts` documents the contract at the top
  and exposes `getSpecVisibility(scope)`, `saveSpecVisibility(scope, input)`,
  `deleteSpecVisibility(scope)`, `getSpecVisibilityKeys()`; `specVisibilityScopePath` maps
  `{kind:'contact'}` / `{kind:'segment'}` / `{kind:'default'}` to
  `/api/v1/user-management/spec-visibility/contacts/{id}` / `/segments/{code}` / `/default`.
  Errors go through `extractApiError`.
- **AC-2 [FE card]** `components/spec-visibility/SpecVisibilitySection.tsx` renders the
  source badge (`Contact override` / `Market segment: <name>` / `Default`), the rule toggle
  with exactly Show only / Hide these (non-deselectable, disabled while saving), the key
  picker with registry labels (no key slugs, no UUIDs in the DOM), and a "Hidden today:"
  line listing the effective hidden labels, or "Nothing hidden".
- **AC-3 [FE card]** Placeholders name the reading in force: Show only + null "All specs",
  Show only + [] "No specs", Hide these + [] "All specs". Flipping the rule carries the
  ticked keys across; Hide these with no chips -> Show only yields null, never [].
- **AC-4 [FE card]** Save sends `{spec_keys: ids-or-null, excluded_spec_keys: null}` under
  Show only and `{spec_keys: null, excluded_spec_keys: ids}` under Hide these. Dirty
  tracking: a rule flip alone enables Save; flipping back restores clean. Remove is present
  only when an override row exists at this tier and is a deferred pending action (countdown,
  no confirm dialog).
- **AC-5 [FE card]** States: loading skeleton, error with the extracted message, inherited
  (badge names the tier, Save turns the values into a row), override. Usable and non-clipped
  at 375px and 1280px (full-width cell like the stock card).
- **AC-6 [FE placement]** The card appears on the contact detail page directly under Stock
  visibility, on the market segment admin page per segment, and at Settings >
  Spec visibility (nav entry beside Stock visibility).
- **AC-7 [UX]** No motion beyond the shared `SearchableMultiSelect` and button pressed states.
  No explanatory copy in the card.

## Phase 2 (BE, tests red first)

- **AC-8 [BE]** Migration `510_spec_visibility_policies` (`down_revision =
  "ptag_0006_revisions"`, re-parented at PR time) creates
  `spec_visibility_policies`: `id`, `contact_id` FK `respond_contacts.id` CASCADE nullable,
  `segment_code` FK `market_segments.code` ON UPDATE/DELETE CASCADE nullable, `spec_keys`
  ARRAY(Text) nullable, `excluded_spec_keys` ARRAY(Text) nullable, timestamps; CHECK
  `ck_spec_visibility_policies_one_tier` (`contact_id IS NULL OR segment_code IS NULL`),
  CHECK `ck_spec_visibility_policies_one_rule` (`spec_keys IS NULL OR excluded_spec_keys IS
  NULL`); three partial unique indexes (contact, segment, default). Seeds: the default row
  `excluded_spec_keys = ['thickness','board_thickness']` and the `project` segment row
  `excluded_spec_keys = []` (inserted only if that segment code exists). A row with both
  lists non-null raises IntegrityError. Downgrade drops the table.
- **AC-9 [BE]** `resolve_policy(db, contact_id, space_id)` in
  `app/services/spec_visibility.py`: contact override beats segments beats default;
  segments merge as intersection of non-null `spec_keys` and union of non-null
  `excluded_spec_keys`; `source` / `source_label` name the tier (segment NAME, never code).
  An unresolvable contact returns the default policy (fail closed).
- **AC-10 [BE]** `hidden_keys(policy, registry_keys)` returns the set of registry keys the
  contact may NOT see: Show-only null -> nothing hidden except the Hide list; Show-only
  list -> every key not in it (plus the Hide list when a merged policy carries both);
  Show-only [] -> every key. A key that has since left the registry is ignored.
- **AC-11 [BE routes]** `app/api/v1/user_management/spec_visibility.py`, mounted at
  `/api/v1/user-management/spec-visibility`: `GET /effective?contact_id&space_id` (api-key
  allowed, `user_management.contacts.view`), `GET|PUT|DELETE /contacts/{id}`,
  `GET|PUT|DELETE /segments/{code}`, `GET|PUT /default`, `GET /keys` (active registry keys
  as `[{key, label}]` sorted by label). Writes need `user_management.contacts.edit`. No new
  permission slug.
- **AC-12 [BE routes]** PUT body requires both `spec_keys` and `excluded_spec_keys`
  (nullable); both non-null -> 422 `Pick specs to show or to hide, not both.`; an unknown
  or inactive key -> 422 naming it; an unknown segment code -> 404. Response
  `{effective, override}` where each policy carries `specs: [{key,label}] | null`,
  `excluded_specs: [{key,label}] | null`, `hidden: [{key,label}]`, `source`,
  `source_label`. `response_model` declares every field (field-drop test).
- **AC-13 [BE routes]** `excluded_spec_keys: []` round-trips as `[]` (nothing hidden at that
  tier). DELETE on a tier that inherits returns 404; the audit log records PUT and DELETE.
- **AC-13b [BE routes]** The record action key `spec_visibility_policy.remove` (registered in
  `app/services/record_actions.py` like `stock_visibility_policy.remove`) deletes the
  contact-tier row and the segment-tier row when run for each, refuses the default tier, and
  writes the same audit row the DELETE route writes.
- **AC-14 [BE chatbot]** `check_access` adds `hidden_spec_keys` (sorted list) to
  `ctx.access`, resolved once per turn with the same contact resolution as field reveals.
- **AC-15 [BE chatbot]** `_project_product_specs` drops every `spec:<key>` field whose key
  is hidden before the "Specs:" summary is built and before asked-word matching; hidden keys
  are also removed from the vocabulary used for matching, so a hidden key never counts as a
  hit. A product envelope for a contact hiding `thickness`, no attribute asked: the Specs
  line names every populated key except Thickness.
- **AC-16 [BE chatbot]** Asked word naming a hidden key (exact key/label, or every asked
  token contained in it, the same rule as a hit): one `spec_misses` entry `{key:
  "spec_hidden:<key>", label, value: "not available"}`, rendered once after the items; no
  "not recorded for ..." line and no product codes are listed for it. A word naming a
  visible key behaves exactly as today.
- **AC-17 [BE chatbot]** The turn trace gains `spec_visibility: {hidden: [...], dropped:
  [...]}` beside `reveals`, listing the keys actually removed from the envelope.
- **AC-18 [BE chatbot]** Spec fallback (`resolve_entity` with `spec_fallback: true`) sends
  `hidden_spec_keys` from `ctx.access`; the resolve route drops extracted specs on hidden
  keys before `search_specs` and strips hidden keys from each candidate's `summary`. A
  retail contact typing "sink 0.8mm bowl" does not get a thickness-ranked match; a project
  contact does.
- **AC-19 [BE]** The MCP presenter, dealer kit `spec_lines` / `product_specs`, price tags,
  the customer portal and the staff product page are byte-identical (a test on
  `tag_data_service.product_specs` for a product carrying `thickness` still lists it).
- **AC-20 [E2E]** Chatbot console check (`documentation/agents/chatbot-verification.md`)
  with two contacts on a product carrying `thickness` and `board_thickness`: a retail-segment
  contact asking "SRTKS8825 spec" gets no thickness in the Specs line and "Thickness: not
  available" on a direct ask; a project-segment contact gets both values. Evidence saved
  under `documentation/plans/chatbot/evidence/spec-visibility/`.
- **AC-21 [browser]** Via sidebar from `/`: Contacts > a contact > Spec visibility: badge
  reads Default with "Hidden today: Thickness, Drainer board / countertop thickness"; press
  Show only, tick Material, Save, reload: Contact override, one chip, "Hidden today" lists
  every other key. Remove (countdown lapses), reload: back to Default. Market segments >
  Project shows "Nothing hidden". Settings > Spec visibility shows the default. 375px and
  1280px.

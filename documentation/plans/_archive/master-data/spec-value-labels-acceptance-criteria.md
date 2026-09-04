# UAC - Spec registry: a display label per value

**Companion to:** `PLAN-spec-value-labels.md`
**Status:** SUPERSEDED 2 Sep 2026 - folded into `spec-workbench-redesign-acceptance-criteria.md` Groups D and E. Kept for the record; do not build from this file.
**Legend:** `[BE]` pytest · `[FE]` vitest · `[E2E]` agent-browser · `[MIG]` migration · `[T]` CI guard.

## Journey

**Actor:** master-data staff with `master_data.spec_registry.edit`, on
Master data > Product specifications > a key (e.g. Seat cover material).

1. In **Words customers say**, each value row's left cell (today static "Pp") is a text
   input. They type `PP`. Same for `uf` -> `UF`. Save once, the same Save the words use.
2. Anywhere a product's value is shown (product Specifications tab, spec table cells, flyer
   spec proposals, spec verification list) it now reads `PP`. The stored slug `pp` is
   untouched: search, the parser, derivation and the ranker still compare on `pp`.
3. Clearing the input returns the row to the automatic wording (`Pp`).

One decision: the wording. Nothing else is asked.

## Group A - Storage and API (S1)

### AC-A.1 [MIG] Column
`product_spec_registry.value_labels JSONB NOT NULL DEFAULT '{}'`. Existing rows read `{}`.
Chained on `445_flyer_reading_code_overrides` (see PLAN "Migration order"). Downgrade drops it.

### AC-A.2 [BE] Read
`GET /master-data/spec-registry` (list and single) carries `value_labels` as
`{ "<slug>": "<label>" }`. A test asserts the field is present in the serialised response.

### AC-A.3 [BE] Write
`PUT .../spec-registry/{spec_key}` accepts `value_labels: dict[str, str]`. Editable on seed
AND user rows (staff-owned, like `user_synonyms`; never seed-repaired). Labels are trimmed;
an empty label drops the key; a key that is not one of the row's values (merged allowed
values, or a key present in synonyms/user_synonyms for keys without a closed list) is
rejected 422 `spec_registry_label_unknown_value`. Length cap 60.

### AC-A.4 [BE] Seed repair leaves labels alone
Given a seed row with `value_labels = {"pp": "PP"}`, when the startup seed repair runs,
then the label survives.

### AC-A.5 [BE] Permission
PUT with labels needs `master_data.spec_registry.edit` (the slug the route already uses);
403 without.

## Group B - Frontend (S1)

### AC-B.1 [FE] `readableValue` / `readableEntry` take labels
`readableValue('pp', undefined, {pp: 'PP'})` -> `PP`; `readableValue('pp')` -> `Pp`
(fallback unchanged); list values map element-wise; unit still appended; numbers and
booleans unaffected.

### AC-B.2 [FE] Editor row
In `SpecKeyEditor` "Words customers say", the left cell of each value row is an `Input`
whose value is `value_labels[value] ?? ''` and whose placeholder is the automatic wording
(`readable(value)`). Typing changes the draft; Save sends `value_labels` in the same PUT
as the words. Struck-through (dropped) rows keep their input disabled. Boolean `true` row
keeps "When true".

### AC-B.3 [FE] Every value display uses the label
Product Specifications tab (`SpecTable` -> `SpecValueCell`, including the enum select's
option labels), `ProductProposalGroup`, `FlyerSpecReviewScreen`, `SpecVerificationList`,
`SpecProposalReview`: a value with a label renders the label. Each screen reads labels
from the registry it already loads (or the shared registry query where it did not).

### AC-B.4 [E2E]
Sidebar from `/`: set `PP` on Seat cover material, Save; open a Water Closet product whose
seat material is `pp`; Specifications tab shows `PP`. Clear the label, Save, reload: `Pp`.
375px and 1280px.

## Out of scope
- Chatbot / MCP presenters (backend) keep the slug wording. Trigger: a customer-facing
  reply that reads "pp seat". Backlog.

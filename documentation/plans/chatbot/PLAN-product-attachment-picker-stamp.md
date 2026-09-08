# PLAN: product_attachment picker stamps "has / no <type>" per line (repair)

Status: IMPLEMENTED, AC-8 verified in the browser 8 Sep 2026 (branch
fix/product-attachment-picker-stamp).
Issue #750 (owner-observed on prod, relayed from sorento-crm-n8n#97). Owner's words: "my problem is why it doesn't have has / no product
photo stamping".
UAC: `product-attachment-picker-stamp-acceptance-criteria.md`.

## What exists (this is a repair, not a build)

The stamp is already built. `answer.build_suggest_offer` has a 4th surface for the
require-specific picker (`answer.py` ~3331) that suffixes each numbered line with
`- has {noun}` / `- no {noun}` from a probe-before-offer, and `miss_suggest.dym_transform`
has a `picker` lane for exactly this gate (`picker_cands()`), enabled for
`product_attachment` in `DOMAIN_PROBE`.

## Root cause (measured against the real lane on the 7 Sep prod copy)

Console turn "photo for srtwc286": resolver 10 products + attachment type "Product Photos"
(uuid 90e76894), gate `require_specific`, `dym_transform` `probe_lane: picker`,
`probe_needed: True`, `probe_uuid_keyed: True`, probe answered one row (SRTWC286-SH),
`dym_annotate` `ok: True, key_mode: uuid`, `dym_available_codes = [<uuid of SRTWC286-SH>]`.

Then the render: `answer.py:3343` keys each line by product CODE
(`key = _ms_norm(match.group(1))`) and tests it against `dym_probed` / `dym_has`, which for
this domain are UUID sets (`miss_suggest.py:764-776`, `probe_uuid_keyed` set at
`miss_suggest.py:534` for `product_attachment` on the `d1` and `picker` lanes). 10 of 10
lines miss and take the "unprobed renders BARE" branch. Nothing upstream skipped.

The same mismatch breaks the did-you-mean surfaces for this domain (`answer.py:3413`,
`3527-3541`). Environment independent; `probe_uuid_keyed` and the 4th surface landed in the
same commit (981860f7e, #674), an ancestor of prod, so the picker has never stamped for
this domain anywhere.

Second defect behind the first: `DOMAIN_PROBE["product_attachment"].noun` is `None`, so the
render falls back to `attachment_noun()` = the customer's own raw token ("- has photo"),
not the resolved type name the owner asked for ("- has Product Photos").

Failing test already in the lane: `tests/chatbot/test_product_attachment_picker_stamp.py`
(real resolver, gate, transform, annotate, miss lane, composer; only the MCP client is
monkeypatched to answer from seeded rows).

## Decisions

1. **Translate uuid to code once, where both sets are built.** `miss_suggest._annotate`
   (uuid-keyed branch) exposes the `dym_probe_row_keys` it already holds
   (`{uuid, code, company}` per candidate) on its output. `build_suggest_offer`
   (`answer.py` ~3318) builds `dym_probed` / `dym_has` in CODE space from those row keys
   when `dym_probe_meta.key_mode == "uuid"`. A code that maps to more than one uuid, or
   that appears in `dym_ambiguous_uuids` / `dym_ambiguous_codes`, is left OUT of both sets
   so its line keeps rendering bare (twins are never promised). Lines 3344, 3413 and
   3527-3541 then work unchanged, so all three surfaces are repaired by one change.
2. **Company-suffixed lines.** `gate.py` (~640-670) appends " (Company)" to a picker line
   whose code is duplicated in the option set, `product_attachment` only. The code-space
   key strips that suffix and joins on the composite (code, company) the annotator's row
   keys already carry; a line whose composite is not in the probed set renders bare.
3. **Noun = the resolved attachment type's name**, taken from the scoping entity's `code`
   in `dym_probe_entities` (what the probe was actually filtered on), falling back to
   `attachment_noun()` when there is none. `_CERT_PREFIX_RE`'s certificate family handling
   stays: a resolved name matching it still renders "certificate". So the owner's turn
   reads `1. SRTWC286-SH-200 - no Product Photos` ... `4. SRTWC286-SH - has Product Photos`.
4. **Suffix, never reorder or drop.** The numbers are the pick affordance and
   `suggest_last_result_set` / the idx contract are the gate's; the render only adds a
   suffix. (The incoming SIBLING picker sorts has-first because it builds its own list;
   this picker does not.) The trailing sentence when nothing has the type stays as the
   4th surface already does it, if it does; otherwise none is added.
5. Scope: all three surfaces (picker + both D1 renders) since the fix is the shared point.
   No change to `DOMAIN_PROBE`, the gate, the probe args, the MCP tool or the parser.

## Work

- `app/services/chatbot/lanes/business/miss_suggest.py::_annotate` (expose row keys).
- `app/services/chatbot/lanes/business/answer.py::build_suggest_offer` (~3310-3345 code-space
  sets + noun; verify 3413 and 3527-3541 need nothing).
- Tests: the existing failing test goes green; add the D1 case, the company-suffix case,
  the twin-code case, and the noun/certificate case (see UAC). No FE change.

## What it cost, on landing

- `_annotate` carries two new keys (`dym_probe_row_keys`, `dym_probe_type_name`) and
  `build_suggest_offer` strips them again with the rest of `_DYM_CTRL_KEYS`, so that node's
  own captures stay byte-equal. The `dym-annotate` captures cannot: 5 of the 16 graded ones
  now carry a key n8n's body does not emit, so they are registered field-scoped in
  `tests/chatbot/divergences.py` (measured: those 5 are exactly the ones that differ, and
  the addition is their only disagreement).
- AC-3 is driven from a LITERAL resolver payload rather than a real resolve, because the D1
  surface needs a token with no `matches` and trigram `alternatives`, and the blank test
  schema's `search_path` excludes `public` where `pg_trgm` lives, so `similarity()` cannot
  run there. The gate, transform, annotator and composer are all real on that test.
- The D1 single-token surface sorts has-first when it annotates. That sort is the shipped
  behaviour for every already-stamped domain and it runs before the roster and the pick
  round trip are derived, so it is left alone; decision 4's no-reorder rule is about the
  require-specific picker, whose numbering is the gate's.

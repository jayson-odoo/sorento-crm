# PLAN: spec visibility policy (which product spec keys a contact may see)

Status: PR open 14 Sep 2026 (all slices done, reviewed, verified); awaiting merge
Lane: `.claude/worktrees/spec-visibility`, branch `feat/spec-visibility-policy`, base `origin/main`
UAC: `spec-visibility-policy-acceptance-criteria.md` (alongside)
Sibling: `scripts/load_kitchen_sink_thickness.py` (branch `chore/sink-thickness-loader`) creates the
`board_thickness` and `surface_texture` registry keys and loads the owner's sheet. Independent lane;
this plan only assumes the key names.

## Journey

See the UAC's Journey section (one copy). In one line: a CS admin hides a few spec keys from a
contact, a market segment, or everyone, from a card shaped like Stock visibility; the chatbot then
omits those keys for that contact and says "not available" on a direct ask.

## Evidence (measured on origin/main, 13 Sep)

- Specs: one row per product in `product_specifications.values` keyed by
  `product_spec_registry.spec_key` (49 active keys). `thickness` (numeric mm) carries the bowl
  gauge on 116 products, all derived from `...X0.7MM` in descriptions; `board_thickness` and
  `surface_texture` arrive with the loader lane.
- The chatbot reads specs in exactly one module: `app/services/chatbot/lanes/business/fetch.py`.
  `include_specs` opt-in at :558-563 (products tool, `check_product` / `master_products`),
  projection `_project_product_specs` :1118-1270 (the "Specs:" summary line, asked-word matching,
  `spec_misses` "not recorded for ..."), call site :1371-1375. The restricted-field drop at
  :1281-1356 reads `ctx.access.attributes` and is silent.
- `ctx.access` is built once per turn by `check_access` (`app/services/chatbot/head/access.py`
  :98-128), which already resolves the contact for field reveals.
- Second read path: `resolve_gate.py` :323/:457 sets `spec_fallback: True` and
  `app/api/v1/system/references.py` :2383-2444 runs `search_specs` with extracted specs; no
  visibility filter exists there.
- Nothing else the customer sees carries specs: the customer portal returns code/name/category
  only; dealer kit / price tags read `tag_data_service.product_specs` for STAFF-driven prints and
  the owner ruled them out of scope.
- Contact classification: `market_segments` (retail 30 contacts, project 30, untagged 41 of 98) is
  the owner's axis. The chatbot has never read market segment (zero hits under
  `app/services/chatbot/`); `respond_contacts.market_segments` is a plain M2M, resolvable
  in-process.
- Precedent copied: `StockVisibilityPolicy` (`app/models/access.py` :763-869) three tiers, include
  OR exclude list per row (CHECK), partial unique per tier; `app/services/stock_visibility.py`
  `resolve_policy` / `_merge_access_type_rows`; shared card
  `components/stock-visibility/StockVisibilitySection.tsx` with `scope` prop; routes under
  `app/api/v1/inventory/stock_visibility.py` reusing existing permission slugs.
- Not copied: `ContactFieldReveal` (per contact only, allow-list only, default deny; the owner
  needs a Hide list and a per-type default). Its enforcement seam (drop in `fetch.py`, trace in
  `lanes/business/__init__.py` :395-412) is reused.

## Decisions

| Question | Decision |
|---|---|
| Tier axis | Contact override > merged market segments > global default. Owner's call (13 Sep): retail/project is the vocabulary; access types stay for promotions/attachments/stock. |
| Storage | New table `spec_visibility_policies` (migration `510_spec_visibility_policies`, `down_revision = "ptag_0006_revisions"`, origin/main head when the lane was cut; re-parent at PR time), columns per AC-8. Keys stored as registry `spec_key` text, validated against the active registry on write; a key later removed from the registry is ignored on read. |
| Default | Ships closed: default row hides `thickness` + `board_thickness`; `project` row hides nothing; retail and untagged inherit the default. Seeded in the migration, editable afterwards (staff-owned, never seed-repaired). |
| Merge | Same as stock: intersection of Show-only lists, union of Hide lists, both carried; label = first segment name by sort order among the deciding rows. |
| Resolution output | `SpecPolicy(spec_keys, excluded_spec_keys, source, source_label)` + `hidden_keys(policy, registry_keys) -> frozenset`. The chatbot only ever consumes the hidden set. |
| Chatbot seam | `check_access` adds `hidden_spec_keys` to `ctx.access` (one resolution per turn, same contact lookup as field reveals, fail closed to the default policy). `_project_product_specs(e, req_attrs, hidden)` drops hidden `spec:<key>` fields and vocabulary entries first, then runs unchanged. Hidden + asked = one `spec_hidden:<key>` miss line "not available". Trace `spec_visibility`. |
| Spec fallback | `resolve_entity` body carries `hidden_spec_keys`; the resolve route filters extracted specs and candidate summaries. Free-term ranking stays. |
| Customer wording | "not available" on a direct ask (owner's call); lists omit silently, same posture as restricted fields. |
| Routes | `app/api/v1/user_management/spec_visibility.py` mounted at `/api/v1/user-management/spec-visibility` directly in `app/api/v1/__init__.py` with `require_module_enabled_with_api_key("base")`, NOT through `user_management.router`: that router's module gate depends on `get_current_user` and 401s any X-API-Key caller before `/effective` runs (measured in S2). Perms reuse `user_management.contacts.view` / `.edit` (field reveals precedent). `GET /keys` serves the picker so a contacts admin does not need `master_data.products.view`. |
| PUT body | `{spec_keys: list|null, excluded_spec_keys: list|null}`, both required-nullable, never both non-null (422 `Pick specs to show or to hide, not both.`). |
| Card | New `components/spec-visibility/SpecVisibilitySection.tsx`, a sibling of the stock card, not a generalisation of it: no mode, no hide-zero, no presets, one picker, plus the "Hidden today:" line. Two cards sharing a `scope` prop convention is the reuse; a shared "policy card" abstraction waits for a third. |
| Placement | Contact page under Stock visibility (full-width cell); market segment admin page per segment; Settings > Spec visibility beside Stock visibility. Access tab untouched. |
| Out of scope | Dealer kit, price tags, customer portal, staff product page, MCP presenter, n8n, access-type tier, per-value hiding, RAG (the chatbot no longer queries embeddings; the external `/rag` endpoint is n8n-only and unchanged). |
| Motion | None. Shared primitives only. |

## Slices

- **S1 FE (Phase 1, mocked)**: `services/specVisibilityService.ts` (contract doc at top, mock
  adapter), `hooks/useSpecVisibility.ts` (`useSpecVisibilityQuery`, `useSpecVisibilityMutations`,
  `useSpecVisibilityKeys`), `components/spec-visibility/SpecVisibilitySection.tsx`, placement in
  the three pages, settings nav entry. AC-1..AC-7. Verified in agent-browser via sidebar.
- **S2 BE (Phase 2, tester first)**: migration 510 + model, `app/services/spec_visibility.py`,
  routes, `check_access`, `fetch.py` projection + trace, spec fallback, then swap the FE mock for
  `api-client`. AC-8..AC-19.
- **S3**: reviewer + security-reviewer (contact gating + api-key route) + browser verification +
  chatbot console check, in parallel, once. AC-20, AC-21. Guide-writer updates the contacts guide.

## Tests (Phase 2, `tester` writes them red first)

Backend:
- `tests/test_spec_visibility_policy.py`: AC-8 (migration CHECKs + seeds), AC-9 (precedence,
  merge, segment label, unresolvable contact), AC-10 (hidden set for each reading), AC-11..AC-13
  (routes, 422 wording, 404s, response_model field-drop, audit rows). Scratch schema via
  `tests/_pg_fixture.py`; seeds its own contact, segments, registry keys.
- `tests/chatbot/test_spec_visibility_projection.py`: AC-14 (`ctx.access.hidden_spec_keys`),
  AC-15 (summary line omits hidden), AC-16 ("not available" line, no codes; visible key
  unchanged), AC-17 (trace).
- `tests/test_spec_fallback_hidden_keys.py`: AC-18.
- `tests/test_dealer_kit_tag_data_specs_unfiltered.py`: AC-19.

Frontend:
- `services/specVisibilityService.test.ts`: AC-1, AC-4 bodies.
- `components/spec-visibility/SpecVisibilitySection.test.tsx`: AC-2, AC-3, AC-4, AC-5.

## DoD

Mock swapped and verified with real data; default + project rows exist after migrate; no new
permission; every response field asserted; sidebar verification at 375px and 1280px; console
check evidence filed; memory + plan Status updated; worktree gc after merge.

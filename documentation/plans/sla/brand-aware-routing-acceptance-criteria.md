# Brand-aware escalation routing (CRM half, Option B) - acceptance criteria

> Status: REVISED 2026-08-17 - captain pivot: brand tags live on TEAM MEMBERS (multi-select,
> like market segments), NOT on tier rows. The row-level Brand select/badge and the
> agent_teams.brand_code column are REMOVED. Untagged member serves every brand; when no member
> matches the resolved brand the whole team round-robins. The ACs below are restated for the
> member-level design; row-level ACs (former AC-R1..R8, AC-F1..F4) are superseded.
> Source: scout report `brand-aware-escalation-routing/report.md` (firstmate data dir) and the
> captain's decisions of 2026-08-16 (D1 = Option B, D2 T2/T3 shared, D3 no brand -> all-brands
> row, D5 all-brands T1 of `marketing_promotion` = today's `_sorento` T1, D6 company_id override).
> Context: company-aware routing (`company-aware-assignment-routing-acceptance-criteria.md`,
> migration 320) already partitions team-set rows by company. Brand is a SECOND, orthogonal axis:
> Cabana and Mocha are brands under the Sorento company; the Mocha company carries Mocha only.
> The n8n half (sending `brand_code` / `company_id`) is a separate task; nothing here touches n8n.
> Guardrail (unchanged from 320): routing must never break. Every step degrades to a defined row.

## Journey

### The customer - never sees any of this

Messages the one WhatsApp number about a product or a promotion. They name a product code
(or a brand, or nothing). They are never asked "which brand".

1. Their question is not answerable from the catalogue, the bot offers "escalate to marketing".
2. They say yes. The person who picks it up is the one who actually handles that brand.

### n8n - sends what it already resolved

The spine already resolves the product (`resolve-entity`) and therefore knows its brand and its
company. After the n8n follow-up it sends `POST /external/next-assignee` with the SAME base
team-set key it sends today (`marketing_product`, `marketing_promotion`) plus two optional fields:
`brand_code` (lower-case string, or null when unknown / multi-brand) and `company_id` (uuid, or
null). It then creates the tracker with the same two fields.

1. It never learns which brand rows exist. Unknown brand is the CRM's problem, not n8n's.
2. The response echoes the brand and company the CRM actually routed with, so a misrouting is
   diagnosable from the n8n execution log alone.
3. Old workflow versions that still send `marketing_promotion_mocha` keep working for one
   release: the CRM reads the suffix as `marketing_promotion` + brand `mocha`.

### The assigned marketer - only their own brand's work

1. A Mocha item lands on Kia Yee, a Sorento item on Tay Zhi Yang, a Cabana promo on Aqi.
2. When it breaches SLA it escalates up the SAME team set: tier 2 / 3 rows are shared across
   brands unless the admin gave a brand its own tier-2 row.

### The admin - tags people by brand inside the one team set

Opens Access Agents, then the agent, then Team Assignments. Today they see three copies of the
promotion set (`marketing_promotion_sorento` / `_mocha` / `_cabana`) that mean one set.

1. After the migration they see ONE `marketing_promotion` set: three tier-1 rows badged Sorento /
   Mocha / Cabana, one tier-1 row "All brands" (Am's team, today's default), one tier 2 and one
   tier 3 row (All brands).
2. On `marketing_product` they add a tier-1 row, pick the team that holds Kia Yee, and set its
   Brand to Mocha. The existing tier-1 row stays "All brands" (Zhi Yang's team, so Sorento and
   unknown both land there); optionally they badge a Sorento row too.
3. Each tier row has ONE new control: a Brand select (brands of the active company + "All
   brands"). Nothing else on the page changes. The row list shows the brand as a badge.
4. Saving a tier that has brand rows but no All-brands row is rejected with a message naming the
   set and tier: without it an unknown brand has nowhere to go.

### What every stakeholder holds at the end

- Customer: a reply from the right brand's marketer. Nothing else changes.
- Marketer: only their brand's escalations (plus, for the All-brands row, the unknowns).
- Admin: one set per function, brand visible on the row, no more suffixed copies.
- n8n: two optional body fields and two echoed response fields.

## Acceptance criteria

Tags: `[BE]` backend, `[FE]` frontend, `[T]` covered by an automated test, `[E2E]` browser /
stack evidence run.

### Phase 1 - frontend (mocked)

- **AC-F1** `[FE]` Given the Team Assignments editor for an agent, when a tier row renders, then
  it shows a Brand select whose options are the active company's brands (from
  `GET /api/master-data/brands/select`) plus "All brands" (= null); the select is clearable and
  defaults to "All brands". (Journey admin 3)
- **AC-F2** `[FE]` Given a row with `brand_code = "mocha"`, when the read view (AccessAgentDetail
  team list) renders, then that row carries a "Mocha" badge (brand name resolved from the brands
  list, falling back to the upper-cased code); a row with `brand_code = null` carries an
  "All brands" badge. (Journey admin 1-3)
- **AC-F3** `[FE]` Given the admin sets a brand on a row and saves, then the PUT payload row
  carries `brand_code` in lower case (or null). Two rows in the same set + tier are allowed when
  their brands differ; the existing "duplicate code" client guard keys on (code, tier, brand).
- **AC-F4** `[FE]` `[E2E]` The editor and the read view show the SAME row structure (View = Edit
  layout rule): the brand is the only added control, in the same position on both. Verified by
  sidebar navigation at 1280 and 375 px, console clean.

### Phase 2 - backend, test-first

Resolver (`AccessAgentService`, `app/services/user_service.py`):

- **AC-R1** `[BE][T]` Given a set with tier-1 rows {brand `mocha` -> team M, brand null -> team
  A}, when `get_team_id_by_tier(agent, 1, "set", company_id=C, brand_code="mocha")` is called,
  then team M is returned. Case-insensitive: `"MOCHA"` behaves as `"mocha"`.
- **AC-R2** `[BE][T]` Same rows, `brand_code="cabana"` (no cabana row) or `brand_code=None` ->
  team A (the all-brands row).
- **AC-R3** `[BE][T]` Given a set whose tier-1 rows are ONLY brand rows (no null row) and
  `brand_code=None` (or an unknown brand), then the resolver returns None (no silent guess) and
  the external endpoint 404s with the existing "No team found ..." message.
- **AC-R4** `[BE][T]` Given the mocha row exists in company A only and the routing company is
  B where only an all-brands row exists, then B's all-brands row is returned (brand never crosses
  company).
- **AC-R5** `[BE][T]` Every existing call site (13 `get_team_id_by_tier` callers, the
  `resolve_team_with_tier_fallback` / `get_user_tier_in_team_set` helpers,
  `list_team_ids_for_agent_code`, `get_tier_team_and_notify`) compiles unchanged with
  `brand_code=None` and behaves exactly as before on sets that have no brand rows (existing
  test suites stay green).
- **AC-R6** `[BE][T]` The tier-less path (`list_team_ids_for_agent_code`) applies the same
  preference: brand-matching rows, else null-brand rows.
- **AC-R7** `[BE][T]` `set_agent_teams` accepts `brand_code` per row (stored lower-case, empty
  string -> null); duplicate detection keys on (code, tier, brand); a tier that has one or more
  brand rows and NO all-brands row is rejected with a 422 naming the set and tier.
- **AC-R8** `[BE][T]` `list_agent_teams_with_round_robin_state` (GET `/access-agents/{id}/teams`)
  and `list_agent_teams` return `brand_code` on every row.

External endpoints:

- **AC-X1** `[BE][T]` `POST /external/next-assignee` reads `brand_code` (lower-cased, blank ->
  null) and `company_id` from the body. `company_id` (a valid `companies.id`) overrides the
  contact-derived company with `company_source: "body"`; unknown id -> ignored, existing
  resolution continues. Response echoes `brand_code` (the normalised requested brand or null),
  `brand_matched` (true when a brand row served it, false when the all-brands row did) and
  `team_set_code` (the base code actually used), next to the existing `company_*` fields.
- **AC-X2** `[BE][T]` `GET /external/team-members` accepts the same `brand_code` and
  `company_id` query params and resolves the identical team, so the roster it returns is the
  pool next-assignee draws from (read-only UAC probe).
- **AC-X3** `[BE][T]` Legacy suffixed keys map to base + brand in both endpoints and in tracker
  create: `marketing_promotion_sorento|_mocha|_cabana` -> `marketing_promotion` + that brand.
  An explicit body `brand_code` wins over the suffix-derived one.

Tracker + escalation:

- **AC-T1** `[BE][T]` `POST /sla-management/conversation-sla-tracking` accepts optional
  `brand_code` and `company_id`; the row stores `brand_code` (lower-case or null) and, when a
  valid `company_id` is sent, that company instead of the contact-derived one; the base
  `team_set_code` is stored (suffix stripped per AC-X3). The response includes `brand_code`.
- **AC-T2** `[BE][T]` The RR branch of `create_tracking` (no explicit assignee) resolves tier 1
  with the stored brand (Mocha item -> Kia Yee's row).
- **AC-T3** `[BE][T]` Escalation (`POST /sla-management/integration/escalate` and the manual
  escalate route) resolves the target tier with `brand_code=tracker.brand_code`: with only an
  all-brands tier-2 row it lands there; with a tier-2 row for that brand it lands on that.

Migration:

- **AC-M1** `[BE][T]` `agent_teams.brand_code` (nullable text) and
  `conversation_sla_tracking.brand_code` (nullable text) exist after upgrade; the two partial
  unique indexes now include `coalesce(brand_code, '')`, so (agent, code, tier, company) may
  repeat across DIFFERENT brands but never for the same brand nor twice for "all brands"; the
  model's `__table_args__` mirrors the migration exactly (the scratch-schema fixtures build
  indexes from the model).
- **AC-M2** `[BE][T]` On a fixture copy of today's Sorento configuration (three
  `marketing_promotion_{sorento,mocha,cabana}` sets, distinct tier-1 teams, identical tier-2 and
  tier-3 teams), upgrade yields exactly: `marketing_promotion` T1 rows for brands sorento /
  mocha / cabana keeping their teams, ONE T1 all-brands row pointing at the former `_sorento`
  T1 team, ONE T2 all-brands row and ONE T3 all-brands row, no suffixed rows left, and every
  row of the set carrying the former `_sorento` set's `policy_id`.
- **AC-M3** `[BE][T]` If the suffixed sets disagree at tier 2 (or 3), the `_sorento` row
  becomes the all-brands row and the differing rows survive as brand rows for their suffix
  (nobody's ladder silently changes). If a base `marketing_promotion` row already exists at a
  tier it is kept and wins.
- **AC-M4** `[BE][T]` `conversation_sla_tracking` rows whose `team_set_code` is a suffixed key
  are rewritten to the base key with `brand_code` = the suffix, so an open tracker escalates
  correctly after upgrade. Sets other than the three promotion keys are untouched (byte-for-byte
  row equality asserted for a control set in the fixture).
- **AC-M5** `[BE]` The migration is re-runnable (second upgrade is a no-op), leaves ONE alembic
  head, and its revision id is <= 32 characters. Downgrade drops the columns and restores the
  old indexes; the collapse itself is not reversed (documented in the docstring).

Headline cases (report §4 / §6, asserted end-to-end in pytest against a seeded fixture):

- **AC-H1** `[BE][T]` Mocha company, any item, brand null or "mocha" -> the Mocha company's
  `marketing_product` T1 row (Kia Yee).
- **AC-H2** `[BE][T]` Sorento company, brand "mocha", `marketing_product` -> the mocha row
  (Kia Yee).
- **AC-H3** `[BE][T]` Sorento company, brand "sorento" (or unknown / null), `marketing_product`
  -> the all-brands row (Tay Zhi Yang).
- **AC-H4** `[BE][T]` Sorento company, `marketing_promotion` + brand cabana -> Aqi's row; brand
  null -> Am's row (the all-brands T1 created by the migration).

### Phase 3 - verification

- **AC-V1** `[E2E]` agent-browser evidence run: sidebar -> User Management -> Access Agents ->
  agent -> Team Assignments; add a brand row, save, reload, badge shows; network shows the PUT
  with `brand_code`; console clean at 1280 and 375 px.
- **AC-V2** `[T]` vitest: `AccessAgentFormModal.test.tsx` - the modal renders a Brand select per
  assignment row and emits `brand_code` in the PUT payload (null when cleared back to All brands),
  and two rows sharing (code, tier) but differing on brand both pass the client "tier taken" guard;
  `AccessAgentDetail.test.tsx` - the detail page renders the brand badge and the All-brands badge.

## Revision 2 - member-level brand tags (captain, 2026-08-17, supersedes the row-level ACs)

Journey delta: the admin opens the ONE tier-1 team's member list and tags each member with the
brands they serve via the system's multi-select element (as market segments already work).
Zhi Yang = sorento + cabana (etc), Hasni/Kia Yee = mocha, Am = untagged (serves all). Nothing
else in the journey changes: n8n still sends brand_code + company_id, the tracker still stores
the brand, escalation still climbs the same set.

- **AC2-M1** [BE][T] `team_member_brands` join table mirrors `team_member_market_segments`
  (`team_member_id` FK CASCADE + lower-case `brand_code`, unique pair). Member with zero rows
  serves every brand.
- **AC2-M2** [BE][T] Migration (renumbered `371_brand_member_routing`, single head on top of
  origin/main's latest) keeps `conversation_sla_tracking.brand_code` + suffixed-tracker rewrite,
  creates `team_member_brands`, and collapses the three promotion sets to ONE
  `marketing_promotion` set whose T1 is the former `_sorento` T1 team, MOVING Kia Yee and Aqi's
  memberships into it tagged `mocha` / `cabana`, Am untagged; T2/T3 dedupe and policy cast as
  before; `agent_teams` gains NO brand column and its 320-era unique indexes stay as they are.
- **AC2-R1** [BE][T] `get_next_assignee(..., brand_code=None)`: pool = RR-eligible members whose
  brand tags contain the brand OR who have no tags; empty pool -> whole team; composes with the
  market-segment filter (AND). Cursor is scoped per (segments, brand) so pools rotate
  independently; the legacy `''` cursor is untouched when no brand and no segments.
- **AC2-R2** [BE][T] `get_escalation_assignee_for_tier(..., brand_code)` applies the same pool
  rule at the target tier; called with the tracker's stored brand by both escalation routes, the
  RR create branch and extension-notify (unchanged call sites from revision 1).
- **AC2-R3** [BE][T] Headline cases hold: mocha -> Kia Yee (tagged member), sorento/unknown ->
  untagged members (Am / whole-team fallback), cabana -> Aqi.
- **AC2-X1** [BE][T] External contract unchanged: next-assignee / team-members accept
  `brand_code` + `company_id`; `brand_matched` = true when at least one TAGGED member matched the
  brand (false when the untagged/whole-team fallback served it); team-members roster reflects the
  same pool next-assignee draws from.
- **AC2-F1** [FE][T] Member rows in the team editing surface get a Brands multi-select mirroring
  the market-segment editor; member rows in AccessAgentDetail show brand chips; the tier-row
  Brand select and badges are gone.
- **AC2-V1** [E2E] Evidence run redone member-level: tag a member, save, reload shows chips, PUT
  carries the codes; RR pool respected (team-members probe); 1280 + 375 px clean.

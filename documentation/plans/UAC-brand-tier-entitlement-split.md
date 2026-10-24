# Brand x tier entitlement split - acceptance criteria

> Status: DRAFT 2026-08-15, written FIRST per methodology. **Three decisions are still open and
> are marked D1-D3 below; they block specific ACs, not the whole feature.** No code until the
> user signs off.
>
> Trigger: access entitlement is stored as COMPOUND names (`Sorento Dealer`, `Cabana Dealer`,
> `Mocha Office`, `End User`). One string carries two independent axes, so the WhatsApp bot
> cannot ask a clean question and cannot filter on one axis without the other. Raised from the
> n8n side after three rounds of grilling with the user; their contract doc is
> `sorento_crm_n8n/n8n-workflows-init/plans/crm-ask-access-tier-brand-split.md`.
>
> Decisions locked with the user (via the n8n session, 2026-08-11):
> 1. Two independent per-contact axes: `brands` (subset of sorento, cabana, mocha) and
>    `tiers` (subset of office, dealer, end_user).
> 2. **The brand gate stays.** A Cabana-only dealer must never see Sorento dealer files.
>    Collapsing to tier-only with cross-brand visibility was explicitly rejected.
> 3. Admin configures the two axes **independently** per contact.
> 4. Promotions (and their files) are tagged brand + tier.
> 5. Both filters land on ONE call. Two sequential filtered calls would double latency on the
>    busiest promo path.
> 6. Rollout is **additive**: new fields beside the legacy compound names, never a silent
>    rename or removal. n8n runs a compatibility mapper until we name a cutover.
>
> Decisions verified against data rather than assumed (see "Ground truth" below): brand is NOT
> expressible as company; the compound names DO encode real entitlement for most contacts; the
> company gate and the brand gate can disagree today.

## Ground truth

Measured on the prod-copy database 2026-08-11. These numbers drive the ACs, so re-measure on
prod before the migration runs.

| Fact | Value | Consequence |
|---|---|---|
| Brand vs company | All three brands have products in BOTH companies (CABANA 2423 Mocha / 2429 Sorento; MOCHA-brand products exist under the Sorento company) | Brand and company are cross-cutting. Company scope cannot express any brand restriction. **Never map brand to company.** |
| Entitlement distribution (18 contacts) | 8 hold 1 name, 3 hold 2, 2 hold 3, 5 hold all 7 | 13 of 18 are narrow and intentional. The migration must SPLIT them, not zero them. |
| Narrow-holder shapes (13) | 5x `end_user` only; 4x cross-brand (3x cabana_office+sorento_office, 1x all three office); 4x brand-coherent (3x bare `dealer`, 1x dealer+end_user+sorento_office) | Cross-brand holders exist. All live ones are single-tier multi-brand. Multi-tier cross-brand is unpopulated, not impossible. |
| Legacy token | bare `dealer` means **Sorento Dealer** (3 contacts hold it alone) | A naive `split('_')` mangles it. Map explicitly. |
| Promotion ownership | ALL 29 promotions are owned by the **Sorento** company, including all 14 Cabana-described ones. Mocha: 0. | A Mocha-only-scoped contact sees ZERO promotions regardless of entitlement. See D2. |
| Company scope enforcement | `apply_company_scope` is a router-level dependency on every `/api/v1/*` request (`app/main.py:177`); a `do_orm_execute` filter applies it to every ORM query | One gate, no route opts out. The promotion read and the resolver behave identically. |
| Live blast radius of the two-gate trap | Zero. 26 recent token-bearing contacts swept by n8n, none in the all-empty state | Latent trap, not an active outage. Affects urgency of D2, not its substance. |

## Journey

Four actors. The system's job is to ask the fewest questions it can get away with, and to never
present a document the contact is not entitled to see.

### Aisyah - a Cabana-only dealer (narrow holder, the majority shape)

Arrives from a WhatsApp message: *"cabana kitchen sink promo"*. The system already knows her
contact record, her brands (`cabana`), her tiers (`dealer`) and her companies. Nothing about her
entitlement is asked.

1. **She sends the message.** The bot resolves the entities. Brand comes from her words; had she
   omitted it, her single entitled brand supplies it.
2. **No question is asked.** She holds one tier, so there is nothing to disambiguate.
3. **She receives the Cabana dealer file**, and only that. No Sorento dealer pricing, no
   end-user copy of the same promotion, no office copy.
4. **What she holds at the end**: one PDF, the one she is entitled to. What every other
   stakeholder is told: nothing, this is a read.

### Faizal - office staff across two brands (the live cross-brand shape)

Sends *"bathroom furniture promotion"*, naming no brand. He holds `office` at both Cabana and
Sorento.

1. **No tier question**, because he holds exactly one tier. The pre-split model would ask him to
   pick from five compound options here.
2. **Brand is not guessed.** He named none and he is entitled to two, so he receives the office
   documents for both brands, each labelled with its brand.
3. **What he holds at the end**: two different documents, not two copies of one. This is
   correct, not noise, and is why no brand question is asked (see AC-ASK-03).

### Priya - the CRM admin granting access

Opens a contact record in the CRM. Today she picks from seven compound checkboxes and has to
know that the one labelled `dealer` secretly means Sorento.

1. **She sees two independent controls**: Brands (Sorento / Cabana / Mocha) and Tiers (Office /
   Dealer / End User). Neither list mentions the other axis.
2. **She grants Cabana + Dealer.** She is never required to understand a compound name.
3. **What she holds at the end**: a contact who sees exactly Cabana dealer documents. What the
   system is told: `brands=[cabana]`, `tiers=[dealer]`, and the legacy compound field continues
   to be maintained until cutover so nothing downstream breaks mid-migration.

### Rahman - entitled, but scoped to a company that owns no promotions (the latent trap)

Sends *"promo for SRTWC8152"*. He holds `Cabana Dealer`. His contact record is company-scoped to
Mocha only, and every promotion in the system is owned by the Sorento company.

1. **The company gate filters every promotion row away** before entitlement is consulted.
2. **He must NOT be told "no promotion found."** That sentence is false: promotions exist and he
   is entitled to them. He is told his account access could not be verified for this request,
   and the conversation is escalated to a human.
3. **What he holds at the end**: an honest answer and a human, instead of a confident falsehood.
   Today he would receive "no promotion found" with nothing logged as wrong anywhere.

## Open decisions - BLOCKING

These are the user's to make. Each names the ACs it gates so the rest can proceed.

### D1. Is the `end_user` tier brand-scoped, or globally visible?

Today `End User` carries no brand prefix. n8n assumes the brand axis applies to all tiers
(so an end-user document belongs to a brand like any other). Five contacts hold `end_user` alone,
so this is a real population, not an edge.

- **If brand-scoped** (n8n's assumption): an `end_user`-only contact with no brands is entitled
  to nothing, and the migration must decide what brands those 5 contacts get.
- **If globally visible**: `end_user` documents bypass the brand gate, and an `end_user`-only
  contact sees every brand's end-user pricing.

Gates: AC-MIG-04, AC-FILT-05.

### D2. Should Mocha-company contacts see promotions at all?

All 29 promotions belong to the Sorento company. Three shapes of answer:

- **(a) Intended.** Mocha contacts genuinely have no promotions. Then nothing changes except we
  must ship the scope discriminator so the bot stops saying "no promotion found" (AC-SCOPE-01).
- **(b) Promotions should be company-neutral.** Promotions are a Sorento-group asset visible to
  all companies. Needs a visibility rule, not a re-stamp. **This has an existing sanctioned
  implementation**: `__company_shared__ = True` on the model (`app/models/base.py:103`), already
  used by attachments (`app/models/resources.py:78`) and already honoured by the entity resolver
  (`app/services/entity_resolver.py:3788`). A NULL `company_id` then reads under any scope. No
  new machinery.
- **(c) Promotions should be re-stamped / duplicated per company**, mirroring what was done to
  products on 2026-07-26.

**Evidence that (a) is unlikely to be the real intent.** `company_id` on a `CompanyScopedMixin`
model is **auto-stamped on insert from the request scope** (`before_insert`, see
`app/services/company_scope.py`). So "all 29 are Sorento" records WHO UPLOADED THEM, not a
decision that Mocha may not see them. Nobody chose this. Read (a) as "we accept the artefact",
not as "the artefact expresses intent".

**D2 is an instance of a general question, and the general answer is not uniform.** Two live
issues are the same shape, flagged by the n8n session and verified here:

| | Missing rows | Symptom | Where |
|---|---|---|---|
| #134 | MOCHA has no `purchasing` team | `next-assignee` **404**, ~40% of live intervention requests die after the customer was told help was coming | `next_assignee.py:139-145` |
| #141 | MOCHA has 3 SLA policy bindings, SRT has the full set | conversation-SLA create **400**, one layer later | `resolve_policy_id_for` |
| D2 | MOCHA owns 0 promotions | well-formed **empty 200** | promotion read + resolver |

Same root: **Mocha exists as a routing/scoping company but is not populated with the rows each
flow expects.** So the question deserves a general answer: how should an under-populated company
behave? But the answer must split on a distinction the three cases do not share:

- #134 and #141 are missing **configuration**. Falling back to the default company's team set or
  policy binding is safe, and both issues already propose exactly that plus a `routing_fallback`
  marker. Nothing crosses a data boundary.
- D2 is missing **data**. A runtime "fall back to Sorento's promotions" would show a Mocha-scoped
  contact Sorento-owned rows, which is the precise thing multi-company isolation exists to
  prevent. **Do not answer D2 with a fallback.** The honest options stay (a), (b) or (c), all of
  which are decided once and stamped in the data, not resolved per request.

Also note the failure modes differ in kind: #134 and #141 fail LOUD, so they got filed as bugs.
D2 fails SILENT, which is why it needed the scope discriminator to become visible at all.

Gates: AC-SCOPE-02, and the whole promotion-tagging migration shape. Related: #134, #141.

### D3. Who re-confirms the five all-seven holders, and by when?

The migration must not auto-grant every brand to the 5 contacts holding all seven names, since
that is presumably a label artefact rather than intent. This is a short human decision list.
Needs an owner and a deadline, or the migration blocks on it.

Gates: AC-MIG-03.

## Acceptance criteria

### Contact entitlement model

- **AC-ENT-01** A contact carries two independent entitlement sets: `brands` (subset of the
  brand catalog) and `tiers` (subset of office, dealer, end_user). Either may be empty.
- **AC-ENT-02** The legacy compound `access_levels` names remain readable and correct
  throughout the additive phase. No consumer is forced to migrate on our schedule.
- **AC-ENT-03** The entitlement read endpoint returns the new `brands[]` and `tiers[]` fields
  BESIDE the existing legacy name list. A consumer that reads only the legacy field sees no
  change in behaviour or shape.
- **AC-ENT-04** An empty `brands` set means "no brand entitlement", not "all brands".
  Fail-closed, matching the company scope precedent.

### Admin UI

- **AC-ADMIN-01** The contact entitlement editor presents Brands and Tiers as two independent
  multi-selects. Neither control's options mention the other axis.
- **AC-ADMIN-02** Saving either axis alone is valid; the axes are not co-dependent in the form.
- **AC-ADMIN-03** Existing compound entitlement is shown as its split equivalent, so an admin
  never has to interpret `dealer` as "Sorento Dealer".
- **AC-ADMIN-04** No UUIDs are shown (cursor rule). Brands and tiers render as human labels.

### Promotion tagging

- **AC-TAG-01** A promotion carries a brand and a tier, derived from its existing
  `access_levels` codes where those are unambiguous.
- **AC-TAG-02** A promotion whose codes span several brands (the 7-code rows exist today) keeps
  multi-brand visibility rather than being forced to one brand.
- **AC-TAG-03** Existing `access_levels` on promotions keep working unchanged until cutover.

### Filtering (the read path)

- **AC-FILT-01** The promotions read and the entity resolver accept `brands[]` and
  `access_levels[]` (tiers) on the SAME call. Neither requires a second round trip.
- **AC-FILT-02** Omitted or empty `brands` means "every brand this contact is entitled to". The
  server applies the entitlement gate; the caller never has to enumerate it.
- **AC-FILT-03** A contact entitled to Cabana only never receives a Sorento-tagged promotion or
  file, on any path: promotions list, resolver rows, attachment reads.
- **AC-FILT-04** Resolver promotion rows carry `brand` in `display`, making the prior
  display-only item load-bearing. Product rows already carry it (commit 8c02ec6a1).
- **AC-FILT-05** `end_user`-tier documents follow the rule chosen in **D1**, consistently
  across all three read paths.

### Scope discriminator (ships WITH this, not separately)

- **AC-SCOPE-01** When the request's company scope resolves to zero companies, the response
  carries a machine-readable marker distinguishing "scoped to nothing" from "nothing matched".
  A caller can render "we could not verify your account access" instead of "not found".
- **AC-SCOPE-02** The marker is present on every scoped read path with a defined value set.
  Absence means "no claim" and never "scope was fine" (the #121 omission rule). A consumer must
  be able to treat absence as fail-open without the field losing its discriminating power.
- **AC-SCOPE-03** The marker never leaks the contact's company identities to the caller.
- **AC-SCOPE-04** Adding the marker changes no rows. Same additive property as #121, and it is
  verified the same way (before/after row capture with a discriminator that fails when both
  runs execute the same code).

### Migration

- **AC-MIG-01** Narrow holders' compound names are SPLIT into both axes. `cabana_dealer`
  becomes `{brands:[cabana], tiers:[dealer]}`. Nothing is zeroed, nothing is ignored.
- **AC-MIG-02** The bare `dealer` code maps to `{brands:[sorento], tiers:[dealer]}` by an
  explicit table, never by string splitting.
- **AC-MIG-03** All-seven holders are NOT auto-granted every brand. They are emitted to a
  re-confirmation list per **D3**.
- **AC-MIG-04** `end_user` holders are migrated per **D1**.
- **AC-MIG-05** The migration is re-runnable and idempotent, correcting prior runs rather than
  only filling nulls (repo lesson: JOIN-based "set to correct value where mismatch").
- **AC-MIG-06** Compound names are retired only after n8n confirms its mapper is deleted. We
  name the cutover date; they do not discover it.

### Interaction quality

- **AC-ASK-01** A contact holding one tier is never asked which tier they want.
- **AC-ASK-02** A contact holding several tiers and naming none is asked once, with a numbered
  multi-selectable list of only the tiers they hold. (n8n side; listed here because our
  entitlement shape is what makes it possible.)
- **AC-ASK-03** A contact holding several brands and naming none is NOT asked to pick a brand.
  They receive each entitled brand's documents, labelled. Rationale: those are different
  documents, not redundant copies of one, so an ask would add a turn without removing ambiguity.
  Revisit only if the multi-tier cross-brand shape becomes populated.

## Out of scope

- Category to member-products to promotions resolution (the `shower head` / `paip dapur` class).
  Separately queued; it changes what resolves, not who may see it.
- `ORDER BY` on capped probe queries. Pre-existing, own change, own before/after.
- The ignored `limit` on the primary `_resolve_input` exit. Deliberately preserved.
- Any change to how the company gate itself works. This feature reports on it (AC-SCOPE-01),
  it does not alter it.

## Verification plan

- **pytest**: entitlement read shape (legacy + additive), both-axes filtering on one call,
  fail-closed empty brands, cross-brand isolation on all three read paths, the migration
  mapper against every shape in the Ground truth histogram (including bare `dealer` and the
  all-seven exclusion), the scope marker's presence and value set.
- **Fixtures must be synthesized from the histogram**, not drawn from traffic. Traffic contains
  the all-seven staff cluster and structurally cannot produce the narrow shapes or a
  Mocha-scoped contact. Include one Mocha-company-scoped contact with non-empty entitlement and
  zero visible rows.
- **Corpus replay**: the full-conversation before/after harness from #121
  (`8,253 resolver calls / 23,655 rows`), rerun to prove the read-path change moves no rows for
  contacts whose entitlement is unchanged.
- **Browser**: admin entitlement editor verified with `agent-browser` (headless, bundles its own
  browser). Playwright and Chrome DevTools are not available on this machine and must not be
  used.
- **CI**: seed every chain the tests need. CI's database has no data.

## Next step

User answers D1, D2, D3. Then `PLAN-brand-tier-entitlement-split.md` (schema derived backwards
from the journey above), then Phase 1 FE mock of the admin editor, then Phase 2 backend + tests.

# PLAN: a broaden_axis turn that names a NEW activity domain is a domain switch, not a wander

Status: IN PROGRESS (9 Sep 2026). Lane `fix/chatbot-broaden-domain-switch`.
UAC: `broaden-domain-switch-acceptance-criteria.md`.

## Defect

Prod turn 4325f0db / n8n exec 15711985 (8 Sep 2026): "check stock srtwc286" then "Any incoming"
answered "That would search every stock we have - I need at least one filter". Same defect on
4 Sep, exec 15121180 ("ANY INCOMING" after SRTWT04A), captured as the graded runData fixture
`nodes/sub-semantic-parser/output_exchange/parser-15121180.json` in the n8n corpus, which
therefore pins the WRONG answer today.

Parser v7 raw output on both turns: domain_hint incoming, intent_hint check_incoming,
broaden_axis "all", scope_intent "broaden", entity_op "clear", entities [].

Chain in `app/services/chatbot/head/output_exchange.py` (origin/main 60a473a00):

1. `explicit` (about line 1310) is True because every intent is decisive
   (`NON_DECISIVE_INTENTS` is empty), so the #6 switch-word guard is skipped.
2. The AXIS BROADEN restore block (about line 1397) forces domain_hint back to the previous
   domain whenever `broaden_axis` is truthy and a previous domain exists. The clear rescue
   under it is skipped because scope_intent == "broaden".
3. The executor clears entities. `gate.py` says needs_scope. `answer.py` says "every stock".

## Measured

Across the graded corpus (325 n8n `output_exchange` captures + 98 vendored):

- captures with a non-null `broaden_axis` from the model: 1 (parser-15121180, this defect)
- the restore block's founding execs 13624889 / 13728314 ("all products" mid-order wandering to
  master_products): 0 captures
- the date-widen captures e4381b0d / 98526b81: model domain_hint is NULL, restore fills it
  from the previous state; unaffected by this change.

## Owner ruling (8 Sep 2026)

No message-token or fuzzy guards. They are not typo-proof and the model's domain was already
right. The rule reads parser output fields, previous state and the static `DOMAIN_SPEC`
tables only.

## Rule

In the AXIS BROADEN block, BEFORE the restore, decide whether the model wandered or switched:

```
switched = (
    model broaden_axis == "all"
    and model domain_hint is non-null
    and model domain_hint != previous domain_hint
    and model intent_hint in DOMAIN_SPEC[model domain_hint].intents
    and model domain_hint not in CATALOGUE_DOMAINS
)
CATALOGUE_DOMAINS = {"master_products", "product_attachment", "resource_attachment"}
```

Reasoning: the prompt defines a widen as "KEEP domain_hint", so `broaden_axis` beside a
coherent (domain, intent) pair for a DIFFERENT domain is self-contradictory. A wander lands
on a catalogue domain (naming a KIND of thing: "all products"). Nobody reaches an activity
domain (incoming, order, promotion, inventory, goods_receive, purchase_order, forms, ...) by
naming a kind of thing, so a coherent activity pair is a deliberate switch.

**`broaden_axis == "all"` only (review, blocker B2, 9 Sep 2026).** The first cut fired on
ANY truthy `broaden_axis` (`date`, an entity-hint axis too) and the reviewer measured three
regressions: (1) a `date` widen naming a different domain ("not just August") stuck in the
wandered domain instead of restoring; (2) nulling `broaden_axis` before the reuse executor's
own `all_time` check ("date" axis) silently restored the OLD window instead of wiping it;
(3) nulling `broaden_axis` before the final `ba_final` drop pass (an entity-hint axis, e.g.
"customer") left the named entity undropped. The prompt's widen instruction says KEEP
domain_hint for a `date` widen AND an entity-hint widen just as it does for "all" - so a
differing domain beside either is a known MODEL violation of that instruction, which the
restore block already exists to correct, not a deliberate switch. Only `"all"` has NO such
KEEP clause in the prompt, and only `"all"` has a real capture (exec 15121180). `date` and
entity-hint axes stay on the restore path unconditionally, exactly as before this plan.

When `switched`:

- keep the model's domain_hint and intent_hint; do NOT restore; stamp
  `domain_switch_over_broaden = <previous domain>` (diagnostic).
- broaden_axis -> None, scope_intent -> None (a switch widens nothing).
- entity_op: if the model emitted no `current_message: true` entity and the previous
  state has entities, and EVERY previous entity's hint is outside
  `DOMAIN_BLOCKED_HINTS[new domain]` -> "reuse" (the compatibility test the continuity
  carry already uses, about line 2094). Otherwise leave entity_op as emitted.

When not `switched`: restore block runs exactly as today (date widen, "all products"
mid-order, null model domain).

Place the switched branch so that the final `ba_final` drop (about line 3235) sees
broaden_axis None and drops nothing, and the entity executor (about line 1433) sees the
reuse.

## Fixture

`parser-15121180` flips red. Vendor it into
`sorento_crm_backend/tests/fixtures/chatbot/nodes/output_exchange/parser-15121180.json`
(copy from the n8n corpus, unchanged) so CI grades it, and register a FIELD-scoped
`Divergence(node="output_exchange", fixture="parser-15121180", ...)` in
`tests/chatbot/divergences.py` naming this plan, stripping only the paths this rule moves:
`("output","domain_hint")`, `("output","intent_hint")`, `("output","broaden_axis")`,
`("output","scope_intent")`, `("output","entity_op")`, `("output","entity_op_applied")`,
`("output","entities")`, `("output","broaden_axis_domain_restored")`,
`("output","domain_switch_over_broaden")`, `("output","routing")`,
`("output","domain_signal_source")`. Measure: if a stripped path is byte-equal anyway,
drop it from the tuple; if another path moves, say which and why in the reason.

## Out of scope

Prompt v7 wording, n8n workflow, `explicit` / `NON_DECISIVE_INTENTS`, the switch-word guard.

# PLAN: Planning mode toggle + quantity ledger

Status: In progress (S1-S3). UAC: scm-planning-mode-ledger-acceptance-criteria.md

## Context

The engine already has the mode switch at the policy layer: `scm.reorder_policy.policy_type`
(`reorder_point`/`periodic_review` = auto, `reorder_level` = manual), resolved
sku > abc_xyz_cell > product_class > global. This feature is a REFRAMING on top:
one universal toggle, one ledger popover, sim coverage for both modes. No engine math
changes.

## Slices

### S1 - Planning mode setting (BE + FE)

- BE `app/api/v1/scm/config.py`: extend the existing global-policy read/update pattern
  (see dead_stock_days) with `planning_mode` (GET returns `auto|manual` derived from the
  global row's policy_type; PUT flips policy_type only, `reorder_point` <-> `reorder_level`).
  `periodic_review`/anything else reads as `auto`.
- FE Policies page: "Planning mode" card, two-option control, confirm dialog stating the
  change applies from the next run. Service + hook per layering rules.
- pytest: GET/PUT happy path, permission denial, PUT touches only policy_type.

### S2 - Sim world seeds levels + mode capture

- `world.py`: ScenarioSpec gains a seeded level for every scenario (derive default from
  the demand story, e.g. round(avg monthly x 2) unless the spec already sets
  reorder_level_value; P033 explicitly None).
- `snapshot.py`: record the run's effective global planning mode (from the global policy
  row at snapshot time) as a top-level snapshot key so a mode flip is visible in compare.
- Rerun + verify auto baseline unchanged except the reorder_level snapshot section +
  new mode key; bless. Then flip to manual on the sim DB, run once, sanity-read
  level-based rows (P031 silent, P032 buy 60 unchanged, level-seeded scenarios now
  trigger on level), flip back, run, confirm byte-identical to blessed baseline (C3).

### S3 - Ledger popover (FE, shared PlanLinesGrid)

- Replace the order-qty popover content with the three-block ledger (UAC B). Reuse:
 - decision composition + Adjust logic (S16, planDecisions/coverPlan) for live cover
    lines;
 - existing derivation copy for auto block one;
 - "clears in ~X" phrasing from the suggested-qty cell.
- Forecast add-on: propose `demand_rate x review_days` (auto) / `demand_rate x
  level_cover_months` horizon (manual) - label states the horizon; clicking adds a
  buy-part delta to the decision (bounded input, same as Adjust).
- Vitest: manual vs auto block one; PO shown not counted; cover toggle recomputes; MoQ
  only in buy block; collapsed no-buy state; forecast opt-in adds to buy.

### Verify

- Browser click-through on the sim stack: both modes, both pages (reorder + sim tab),
  console clean, screenshots.
- Sim compare: auto baseline SAME after all changes (except intended snapshot additions,
  re-blessed once).

/**
 * The v1 field descriptor for `<DynamicFilterBuilder>` on the reorder plan grid (S4,
 * PLAN-scm-reorder-oi-feedback-1sep.md). Declared BESIDE `PlanLinesGrid`'s own column
 * defs, per the plan, and consumed nowhere else - a second listing (AC-4.5) declares its
 * own descriptor rather than importing this one.
 *
 * Two of the plan's named v1 fields have no home on `PlanLine` today - "category" (no
 * product category reaches `ReorderRecommendation`) and "days late" (no lateness figure
 * is computed for a plan row; `coverageTimeline.ts`'s `days_late` is a different
 * feature's field on a different shape). Both are declared here anyway, so the builder
 * offers exactly the v1 list the plan named, but their `getValue` returns `null` for
 * every row - `is_empty` on either always matches, and every other operator never does,
 * which is an honest "not on this row" rather than an invented number. Flagged back to
 * the plan rather than silently fabricated.
 */
import { isGroupedLine } from './planLineGrouping';
import { groupDecisionState, type PlanDecisionMap } from './planDecisions';
import { PLAN_LINE_STATUS_LABEL, PLAN_LINE_STATUS_ORDER, type PlanLine } from './planLine';
import type { FilterFieldDescriptor } from '@/lib/list-query/dynamicFilter';

function decisionStateOf(line: PlanLine, decisions: PlanDecisionMap): 'decided' | 'undecided' {
  const decided = isGroupedLine(line)
    ? Boolean(groupDecisionState(line.__group.members.map((m) => m.id), decisions).decision)
    : Boolean(decisions[line.id]);
  return decided ? 'decided' : 'undecided';
}

/**
 * `decisions` is captured in a closure rather than read off the row: whether a line is
 * decided lives in the grid's own decision map, not on `PlanLine` itself, so the caller
 * rebuilds this list (a cheap `useMemo`) whenever `decisions` changes.
 */
export function planLineFilterFields(decisions: PlanDecisionMap): FilterFieldDescriptor<PlanLine>[] {
  return [
    { field_key: 'sku', label: 'Product code', type: 'text', getValue: (l) => l.sku },
    { field_key: 'product_name', label: 'Product name', type: 'text', getValue: (l) => l.product_name },
    // No product category reaches a plan row today - see the module doc above.
    { field_key: 'category', label: 'Category', type: 'text', getValue: () => null },
    { field_key: 'supplier', label: 'Supplier', type: 'text', getValue: (l) => l.supplier.name || null },
    { field_key: 'location', label: 'Location', type: 'text', getValue: (l) => l.warehouse },
    {
      field_key: 'rec_type',
      label: 'Rec type',
      type: 'select',
      options: PLAN_LINE_STATUS_ORDER.map((s) => ({ value: s, label: PLAN_LINE_STATUS_LABEL[s] })),
      getValue: (l) => l.status,
    },
    {
      field_key: 'decision_state',
      label: 'Decision state',
      type: 'select',
      options: [
        { value: 'decided', label: 'Already decided' },
        { value: 'undecided', label: 'Still to decide' },
      ],
      getValue: (l) => decisionStateOf(l, decisions),
    },
    {
      field_key: 'suggested_qty',
      label: 'Suggested qty',
      type: 'number',
      getValue: (l) => (l.purchasable ? (l.status === 'covered_by_stock' ? 0 : l.order_qty) : null),
    },
    {
      field_key: 'reorder_level',
      label: 'Reorder level',
      type: 'number',
      getValue: (l) => l.rec.reorder_level ?? l.rec.master_reorder_level ?? null,
    },
    {
      field_key: 'reorder_qty',
      label: 'Reorder qty',
      type: 'number',
      getValue: (l) => l.rec.master_reorder_quantity ?? null,
    },
    { field_key: 'on_hand', label: 'On hand BRW', type: 'number', getValue: (l) => l.rec.on_hand ?? null },
    { field_key: 'spo_qty', label: 'SPO qty', type: 'number', getValue: (l) => l.rec.incoming_spo ?? null },
    { field_key: 'po_qty', label: 'PO qty', type: 'number', getValue: (l) => l.rec.outstanding_po ?? null },
    {
      field_key: 'project_committed',
      label: 'Project committed',
      type: 'number',
      getValue: (l) => l.rec.project_need ?? null,
    },
    {
      field_key: 'retail_committed',
      label: 'Retail committed',
      type: 'number',
      getValue: (l) => l.rec.retail_need ?? null,
    },
    { field_key: 'unit_cost', label: 'Unit cost', type: 'number', getValue: (l) => l.unit_cost ?? null },
    { field_key: 'currency', label: 'Currency', type: 'text', getValue: (l) => l.currency ?? null },
    // No lateness figure is computed for a plan row today - see the module doc above.
    { field_key: 'days_late', label: 'Days late', type: 'number', getValue: () => null },
  ];
}

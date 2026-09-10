import type {
  ListQueryFilterCondition,
  ListQueryFilterGroup,
} from '@/lib/list-query/listQueryService';

/**
 * PLAN-plan-list-tile-sheet-one-scope.md, AC-5b (owner, 10 Sep: "better to reveal them for
 * flexibility"). The hidden-by-default rows (`plan_scope.hidden_by_default`, backend S6/S7)
 * stay reachable through the grid's OWN Filters builder rather than a retired status preset:
 * when the applied `ListQueryFilterGroup` asks for `rec_type` equals/in a value (the covered
 * status the grid stores as `'covered_by_stock'`), `PlanLinesSection.visibleLines` reveals
 * every row that status can match, hidden-by-default ones included.
 *
 * Walks the group RECURSIVELY - a condition can sit at the top level or nested one (or more)
 * groups deep under either AND or OR, since the dynamic builder lets a buyer wrap a single
 * condition inside a subgroup. `children` mixes conditions and subgroups in one array (the
 * builder's own wire shape); a condition is the leaf that carries `field_key`, a subgroup is
 * the branch that carries `children` instead.
 */
function isCondition(
  item: ListQueryFilterGroup | ListQueryFilterCondition,
): item is ListQueryFilterCondition {
  return 'field_key' in item;
}

export function filterGroupAsksForRecType(
  group: ListQueryFilterGroup | null,
  value: string,
): boolean {
  if (!group) return false;
  for (const child of group.children) {
    if (isCondition(child)) {
      if (child.field_key !== 'rec_type') continue;
      if (child.op === 'eq' && child.value === value) return true;
      if (child.op === 'in' && Array.isArray(child.value) && child.value.includes(value)) {
        return true;
      }
    } else if (filterGroupAsksForRecType(child, value)) {
      return true;
    }
  }
  return false;
}

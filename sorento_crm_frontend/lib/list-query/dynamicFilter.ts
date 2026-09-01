import type { ListQueryFilterCondition, ListQueryFilterGroup } from '@/lib/list-query/listQueryService';

/**
 * The dynamic filter builder (S4, PLAN-scm-reorder-oi-feedback-1sep.md AC-4.1).
 *
 * A `<DynamicFilterBuilder>` composes an existing `ListQueryFilterGroup` - the SAME wire
 * shape `ListQueryFilterDialog` sends the server, so a saved segment's `filters` blob
 * needs no translation - but evaluation here is entirely CLIENT-SIDE against a plain TS
 * field descriptor the consumer declares beside its own column defs. There is no field
 * catalog fetch (`fetchListQueryFields`) and no backend filtering: a reorder-plan line is
 * already fully loaded client-side (`usePlanLines.ts`), so filtering it is a `.filter()`
 * over the already-fetched rows, not a new request.
 */

export type FilterOperator = 'eq' | 'contains' | 'in' | 'gt' | 'lt' | 'between' | 'is_empty';

/**
 * S6 (PR #489 review round): the SAME cap `app/schemas/saved_view.py`'s
 * `SavedViewConfig` validator rejects a saved segment for on the backend - counted
 * root-inclusive (a group with no nested children is depth 1), matching that
 * validator's `_group_depth`. A published default segment auto-applies for every
 * reader (AC-4.4), so this is the UI's OWN guard against building one nobody could
 * turn off without first reaching for "No segment" - the backend cap is the one
 * that actually enforces it.
 */
export const MAX_FILTER_GROUP_DEPTH = 5;

export type FilterFieldType = 'text' | 'number' | 'select';

export interface FilterFieldOption {
  value: string;
  label: string;
}

export interface FilterFieldDescriptor<TRow> {
  field_key: string;
  label: string;
  type: FilterFieldType;
  /** Offered for `eq`/`in` on a `select` field. Required when `type` is `'select'`. */
  options?: FilterFieldOption[];
  /** Operators offered for this field. Defaults to a sane set for `type` when omitted. */
  operators?: FilterOperator[];
  /** The row's own value for this field - the ONLY thing `evaluateFilterGroup` reads. */
  getValue: (row: TRow) => unknown;
}

export const OPERATOR_LABEL: Record<FilterOperator, string> = {
  eq: 'Equals',
  contains: 'Contains',
  in: 'In list',
  gt: 'Greater than',
  lt: 'Less than',
  between: 'Between',
  is_empty: 'Is empty',
};

/** The operators offered for a field that declares none of its own. */
export function defaultOperatorsFor(type: FilterFieldType): FilterOperator[] {
  switch (type) {
    case 'number':
      return ['eq', 'gt', 'lt', 'between', 'is_empty'];
    case 'select':
      return ['eq', 'in', 'is_empty'];
    default:
      return ['contains', 'eq', 'is_empty'];
  }
}

export function operatorsFor<TRow>(field: FilterFieldDescriptor<TRow>): FilterOperator[] {
  return field.operators?.length ? field.operators : defaultOperatorsFor(field.type);
}

export function isFilterGroup(
  node: ListQueryFilterGroup | ListQueryFilterCondition,
): node is ListQueryFilterGroup {
  return node != null && 'children' in node;
}

export function emptyFilterGroup(op: 'and' | 'or' = 'and'): ListQueryFilterGroup {
  return { op, children: [] };
}

function normalise(value: unknown): string {
  return String(value ?? '').trim().toLowerCase();
}

function evaluateCondition<TRow>(
  condition: ListQueryFilterCondition,
  row: TRow,
  fields: FilterFieldDescriptor<TRow>[],
): boolean {
  const field = fields.find((f) => f.field_key === condition.field_key);
  // An unknown field (a segment saved against a descriptor that has since dropped a
  // field) is a no-op rather than a hidden-everything trap.
  if (!field) return true;
  const raw = field.getValue(row);

  switch (condition.op) {
    case 'is_empty': {
      const empty = raw === null || raw === undefined || raw === '';
      // `value: false` reads "is NOT empty" - the same toggle
      // `ListQueryFilterDialog`'s `is_null` operator uses.
      return condition.value === false ? !empty : empty;
    }
    case 'eq': {
      if (raw === null || raw === undefined) return false;
      // S5 (PR #489 review round): a number field compares NUMERICALLY - `eq`/`in`
      // used to `normalise` (stringify) both sides, so "5" and "5.0" (or a value
      // typed with trailing whitespace) read as different values on the very
      // fields `gt`/`lt`/`between` already compare as numbers.
      if (field.type === 'number') {
        const n = Number(raw);
        const t = Number(condition.value);
        return Number.isFinite(n) && Number.isFinite(t) && n === t;
      }
      return normalise(raw) === normalise(condition.value);
    }
    case 'contains':
      if (raw === null || raw === undefined) return false;
      return normalise(raw).includes(normalise(condition.value));
    case 'in': {
      if (raw === null || raw === undefined) return false;
      if (field.type === 'number') {
        const n = Number(raw);
        if (!Number.isFinite(n)) return false;
        const list = Array.isArray(condition.value) ? condition.value.map(Number) : [];
        return list.some((t) => Number.isFinite(t) && t === n);
      }
      const list = Array.isArray(condition.value) ? condition.value.map(normalise) : [];
      return list.includes(normalise(raw));
    }
    case 'gt': {
      // `Number(null) === 0`, so a field with no data source (e.g. "days late" on a
      // plan row) would silently outrank a negative threshold without this guard -
      // the exact fabrication `planLineFilterFields.ts` documents avoiding.
      if (raw === null || raw === undefined) return false;
      const n = Number(raw);
      const t = Number(condition.value);
      return Number.isFinite(n) && Number.isFinite(t) && n > t;
    }
    case 'lt': {
      if (raw === null || raw === undefined) return false;
      const n = Number(raw);
      const t = Number(condition.value);
      return Number.isFinite(n) && Number.isFinite(t) && n < t;
    }
    case 'between': {
      if (raw === null || raw === undefined) return false;
      const n = Number(raw);
      const bounds = Array.isArray(condition.value) ? condition.value.map(Number) : [];
      const [a, b] = bounds;
      if (!Number.isFinite(n) || !Number.isFinite(a) || !Number.isFinite(b)) return false;
      return n >= Math.min(a, b) && n <= Math.max(a, b);
    }
    default:
      return true;
  }
}

/**
 * The whole point: `true` iff `row` matches `group`, recursing into nested groups at any
 * depth (AC-4.1's "fully recursive groups"). `null`/an empty group always matches - the
 * builder's "no filter" state.
 */
export function evaluateFilterGroup<TRow>(
  group: ListQueryFilterGroup | null | undefined,
  row: TRow,
  fields: FilterFieldDescriptor<TRow>[],
): boolean {
  if (!group || !group.children?.length) return true;
  const results = group.children.map((child) =>
    isFilterGroup(child) ? evaluateFilterGroup(child, row, fields) : evaluateCondition(child, row, fields),
  );
  return group.op === 'or' ? results.some(Boolean) : results.every(Boolean);
}

/** How many leaf conditions a group holds, recursively - the toolbar's "N" badge. */
export function countFilterConditions(group: ListQueryFilterGroup | null | undefined): number {
  if (!group) return 0;
  return group.children.reduce(
    (total, child) => total + (isFilterGroup(child) ? countFilterConditions(child) : 1),
    0,
  );
}

/** A fresh condition on `field`, defaulted to its first operator. */
export function newConditionFor<TRow>(field: FilterFieldDescriptor<TRow>): ListQueryFilterCondition {
  const op = operatorsFor(field)[0] ?? 'eq';
  return { field_key: field.field_key, op, value: op === 'is_empty' ? true : undefined };
}

/** One line describing an active group, for the toolbar's active-filter chip. */
export function describeFilterGroup<TRow>(
  group: ListQueryFilterGroup | null | undefined,
  fields: FilterFieldDescriptor<TRow>[],
): string | null {
  if (!group || !group.children?.length) return null;
  const label = (node: ListQueryFilterGroup | ListQueryFilterCondition): string => {
    if (isFilterGroup(node)) {
      const inner = node.children.map(label).join(node.op === 'or' ? ' or ' : ' and ');
      return node.children.length > 1 ? `(${inner})` : inner;
    }
    const field = fields.find((f) => f.field_key === node.field_key);
    const fieldLabel = field?.label ?? node.field_key;
    if (node.op === 'is_empty') return node.value === false ? `${fieldLabel} is not empty` : `${fieldLabel} is empty`;
    if (node.op === 'between' && Array.isArray(node.value)) {
      return `${fieldLabel} between ${node.value[0]} and ${node.value[1]}`;
    }
    if (node.op === 'in' && Array.isArray(node.value)) {
      return `${fieldLabel} in ${node.value.join(', ')}`;
    }
    return `${fieldLabel} ${OPERATOR_LABEL[node.op as FilterOperator]?.toLowerCase() ?? node.op} ${node.value ?? ''}`;
  };
  return label(group);
}

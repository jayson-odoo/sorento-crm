/**
 * R2 - CS-routing predicate builder types + helpers (pure, UI-side).
 *
 * A routing row carries an ordered list of AND-combined predicates evaluated
 * against a form's own field values. Mirrors the backend engine
 * (`app/services/cs_routing_match.py`): operators equals / not_equals /
 * contains / not_contains; an empty predicate list is a wildcard.
 */

export type PredicateOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains';

/** One `{field, operator, value}` predicate (matches the PUT payload shape). */
export interface Predicate {
  field: string;
  operator: PredicateOperator;
  value: string;
}

export type RoutableFieldType = 'lookup' | 'enum' | 'numeric' | 'string';

/** A form field the admin can build predicates against (user-facing fields only). */
export interface RoutableField {
  /** The form column name sent in the predicate (e.g. 'sales_type'). */
  field: string;
  /** Human-readable label shown in the field dropdown. */
  label: string;
  type: RoutableFieldType;
  /** For lookup/enum fields: the selectable option set for the value input. */
  options?: { value: string; label: string }[];
}

export const ALL_OPERATORS: { value: PredicateOperator; label: string }[] = [
  { value: 'equals', label: 'equals' },
  { value: 'not_equals', label: 'does not equal' },
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: 'does not contain' },
];

/**
 * Operators offered for a field type. `contains` / `not_contains` are hidden for
 * enum, numeric AND lookup fields (fixed-option / numeric - substring matching is
 * meaningless there); only free-text string fields get all four.
 */
export function operatorsForFieldType(
  type: RoutableFieldType | undefined,
): { value: PredicateOperator; label: string }[] {
  if (type === 'string') return ALL_OPERATORS;
  return ALL_OPERATORS.filter(
    (o) => o.value === 'equals' || o.value === 'not_equals',
  );
}

/** True when a value input for this field type should be a dropdown of options. */
export function fieldUsesOptionValue(type: RoutableFieldType | undefined): boolean {
  return type === 'lookup' || type === 'enum';
}

/** A row with zero predicates is a catch-all wildcard. */
export function isWildcard(predicates: Predicate[]): boolean {
  return predicates.length === 0;
}

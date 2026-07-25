/**
 * Rule engine types — mirrors the backend camelCase wire contracts
 * (app/rule_engine/schemas.py). The condition tree is stored AS-IS in each
 * consumer's own JSON column (e.g. `automations.conditions_json`).
 *
 * KEEP THE OPERATOR TABLES IN SYNC with the backend `OPERATORS_BY_TYPE`
 * (app/rule_engine/schemas.py) — every operator key here must exist there.
 */

export type RuleFactType =
  | 'string'
  | 'number'
  | 'boolean'
  | 'date'
  | 'enum'
  | 'list';

export type RuleOperator =
  // string / enum
  | 'eq'
  | 'neq'
  | 'contains'
  | 'in'
  | 'not_in'
  // number
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'between'
  // boolean
  | 'is_true'
  | 'is_false'
  // date
  | 'before'
  | 'after'
  // list
  | 'contains_any'
  | 'contains_all'
  | 'not_contains';

/**
 * Operators offered per fact type. MUST match the backend OPERATORS_BY_TYPE:
 *   string  = [eq, neq, contains, in, not_in]
 *   number  = [eq, neq, gt, gte, lt, lte, between]
 *   boolean = [is_true, is_false]
 *   date    = [before, after, between]
 *   enum    = [eq, neq, in, not_in]
 *   list    = [contains_any, contains_all, not_contains]
 */
export const RULE_OPERATORS: Record<
  RuleFactType,
  { value: RuleOperator; label: string }[]
> = {
  string: [
    { value: 'eq', label: 'is' },
    { value: 'neq', label: 'is not' },
    { value: 'contains', label: 'contains' },
    { value: 'in', label: 'is any of' },
    { value: 'not_in', label: 'is none of' },
  ],
  number: [
    { value: 'eq', label: '=' },
    { value: 'neq', label: '≠' },
    { value: 'gt', label: '>' },
    { value: 'gte', label: '≥' },
    { value: 'lt', label: '<' },
    { value: 'lte', label: '≤' },
    { value: 'between', label: 'between' },
  ],
  boolean: [
    { value: 'is_true', label: 'is yes' },
    { value: 'is_false', label: 'is no' },
  ],
  date: [
    { value: 'before', label: 'before' },
    { value: 'after', label: 'after' },
    { value: 'between', label: 'between' },
  ],
  enum: [
    { value: 'eq', label: 'is' },
    { value: 'neq', label: 'is not' },
    { value: 'in', label: 'is any of' },
    { value: 'not_in', label: 'is none of' },
  ],
  list: [
    { value: 'contains_any', label: 'contains any of' },
    { value: 'contains_all', label: 'contains all of' },
    { value: 'not_contains', label: 'contains none of' },
  ],
};

/**
 * Scalar compare operators that may flip to cross-fact mode
 * (`between` / `contains` / list ops stay literal-only).
 */
export const CROSS_FACT_OPERATORS: ReadonlySet<RuleOperator> =
  new Set<RuleOperator>([
    'eq',
    'neq',
    'gt',
    'gte',
    'lt',
    'lte',
    'before',
    'after',
  ]);

/** Groups nest to depth 5 (same guard as the backend validator). */
export const RULE_MAX_DEPTH = 5;

export interface RuleFactOption {
  value: string;
  label: string;
}

/**
 * One whitelisted fact from the registry (`GET /rule-facts?sources=`).
 * `key` is namespaced by source (`promotion.name`, `promotion.accessLevels`);
 * the builder groups the picker by `sourceLabel`.
 */
export interface RuleFactItem {
  key: string;
  label: string;
  type: RuleFactType;
  /** Operators the backend accepts for this fact (subset of RULE_OPERATORS[type]). */
  operators?: RuleOperator[];
  source: string;
  sourceLabel: string;
  /** Enum/list facts carry their selectable options. */
  options?: RuleFactOption[];
}

export type RuleValueKind = 'literal' | 'fact';

export interface RuleCondition {
  kind: 'condition';
  fact: string;
  operator: RuleOperator;
  /** `fact` ⇒ `value` is another fact key of the same type. */
  valueKind: RuleValueKind;
  value: unknown;
}

export interface RuleGroup {
  kind: 'group';
  combinator: 'and' | 'or';
  rules: (RuleCondition | RuleGroup)[];
}

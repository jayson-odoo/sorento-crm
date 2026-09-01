/**
 * `evaluateFilterGroup` - the client-side evaluator every consumer of `<DynamicFilterBuilder>`
 * filters rows through (AC-4.1: every operator, AND/OR, fully recursive groups).
 *
 * A synthetic row shape is used throughout rather than `PlanLine` - the generic evaluator
 * has no reorder dependency and this file proves it by never importing one (AC-4.5). Two
 * fields deliberately return `null` for EVERY row, the same honest-absence pattern
 * `planLineFilterFields.ts` uses for "category" and "days late" (no data source on a plan
 * row today): `is_empty` matches every row, and every other operator matches none - a
 * `null` never satisfies `eq`/`contains`/`gt`/`lt`/`in`/`between` by accident.
 */
import { describe, it, expect } from 'vitest';
import {
  countFilterConditions,
  defaultOperatorsFor,
  describeFilterGroup,
  emptyFilterGroup,
  evaluateFilterGroup,
  newConditionFor,
  operatorsFor,
  type FilterFieldDescriptor,
} from './dynamicFilter';
import type { ListQueryFilterGroup } from './listQueryService';

interface Row {
  id: string;
  title: string;
  status: 'open' | 'closed';
  amount: number | null;
}

const rows: Row[] = [
  { id: '1', title: 'Alpha widget', status: 'open', amount: 120 },
  { id: '2', title: 'Beta gadget', status: 'closed', amount: 40 },
  { id: '3', title: 'Gamma thing', status: 'open', amount: null },
];

const FIELDS: FilterFieldDescriptor<Row>[] = [
  { field_key: 'title', label: 'Title', type: 'text', getValue: (r) => r.title },
  {
    field_key: 'status',
    label: 'Status',
    type: 'select',
    options: [
      { value: 'open', label: 'Open' },
      { value: 'closed', label: 'Closed' },
    ],
    getValue: (r) => r.status,
  },
  { field_key: 'amount', label: 'Amount', type: 'number', getValue: (r) => r.amount },
  // The "not on this row" fields - the same shape `planLineFilterFields.ts` gives
  // "category" and "days late": no data source, so every row's value is `null`.
  { field_key: 'category', label: 'Category', type: 'text', getValue: () => null },
  { field_key: 'days_late', label: 'Days late', type: 'number', getValue: () => null },
];

const row = (id: string) => rows.find((r) => r.id === id)!;

const cond = (field_key: string, op: string, value?: unknown) => ({ field_key, op, value });
const group = (op: 'and' | 'or', children: ListQueryFilterGroup['children']): ListQueryFilterGroup => ({
  op,
  children,
});

describe('evaluateFilterGroup - no filter', () => {
  it('matches everything when the group is null', () => {
    expect(evaluateFilterGroup(null, row('1'), FIELDS)).toBe(true);
  });

  it('matches everything when the group has no children', () => {
    expect(evaluateFilterGroup(emptyFilterGroup('and'), row('1'), FIELDS)).toBe(true);
  });

  it('is a no-op for an unknown field key rather than hiding every row', () => {
    // A segment saved against a descriptor that has since dropped a field.
    const g = group('and', [cond('discontinued_flag', 'eq', 'x')]);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true);
  });
});

describe('evaluateFilterGroup - every operator', () => {
  it('eq: case/whitespace-insensitive match on a text field', () => {
    const g = group('and', [cond('title', 'eq', '  Alpha Widget  ')]);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('2'), FIELDS)).toBe(false);
  });

  it('eq: never matches a null value', () => {
    const g = group('and', [cond('amount', 'eq', 40)]);
    expect(evaluateFilterGroup(g, row('3'), FIELDS)).toBe(false);
  });

  it('contains: substring, case-insensitive', () => {
    const g = group('and', [cond('title', 'contains', 'GADGET')]);
    expect(evaluateFilterGroup(g, row('2'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(false);
  });

  it('contains: never matches a null value', () => {
    const g = group('and', [cond('amount', 'contains', '4')]);
    expect(evaluateFilterGroup(g, row('3'), FIELDS)).toBe(false);
  });

  it('in: value found in the list', () => {
    const g = group('and', [cond('status', 'in', ['closed', 'pending'])]);
    expect(evaluateFilterGroup(g, row('2'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(false);
  });

  it('in: never matches a null value, and a non-array value is an empty list', () => {
    expect(evaluateFilterGroup(group('and', [cond('amount', 'in', [40])]), row('3'), FIELDS)).toBe(false);
    expect(
      evaluateFilterGroup(group('and', [cond('status', 'in', 'not-an-array')]), row('1'), FIELDS),
    ).toBe(false);
  });

  it('gt: numeric greater-than', () => {
    const g = group('and', [cond('amount', 'gt', 100)]);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('2'), FIELDS)).toBe(false);
  });

  it('gt: a null value is never greater than anything', () => {
    expect(evaluateFilterGroup(group('and', [cond('amount', 'gt', 0)]), row('3'), FIELDS)).toBe(false);
  });

  it('lt: numeric less-than', () => {
    const g = group('and', [cond('amount', 'lt', 100)]);
    expect(evaluateFilterGroup(g, row('2'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(false);
  });

  it('between: inclusive, and order-independent bounds', () => {
    const g = group('and', [cond('amount', 'between', [50, 150])]);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true); // 120
    expect(evaluateFilterGroup(g, row('2'), FIELDS)).toBe(false); // 40
    const reversed = group('and', [cond('amount', 'between', [150, 50])]);
    expect(evaluateFilterGroup(reversed, row('1'), FIELDS)).toBe(true);
  });

  it('between: a null value never falls inside any range', () => {
    expect(
      evaluateFilterGroup(group('and', [cond('amount', 'between', [0, 1000])]), row('3'), FIELDS),
    ).toBe(false);
  });

  it('is_empty: true matches a null/undefined/blank value', () => {
    const g = group('and', [cond('amount', 'is_empty', true)]);
    expect(evaluateFilterGroup(g, row('3'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(false);
  });

  it('is_empty: value false reads "is not empty"', () => {
    const g = group('and', [cond('amount', 'is_empty', false)]);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('3'), FIELDS)).toBe(false);
  });
});

describe('evaluateFilterGroup - honest null fields (category / days late have no data source)', () => {
  it('is_empty always matches a field with no data source', () => {
    const g = group('and', [cond('category', 'is_empty', true)]);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('2'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('3'), FIELDS)).toBe(true);
  });

  it('every other operator never matches a field with no data source', () => {
    const never = [
      cond('category', 'eq', 'Anything'),
      cond('category', 'contains', 'a'),
      cond('days_late', 'gt', -1),
      cond('days_late', 'lt', 999999),
      cond('days_late', 'between', [-1000, 1000]),
    ];
    for (const c of never) {
      const g = group('and', [c]);
      for (const r of rows) {
        expect(evaluateFilterGroup(g, r, FIELDS)).toBe(false);
      }
    }
  });
});

describe('evaluateFilterGroup - AND / OR', () => {
  it('AND requires every condition', () => {
    const g = group('and', [cond('status', 'eq', 'open'), cond('amount', 'gt', 100)]);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true); // open, 120
    expect(evaluateFilterGroup(g, row('3'), FIELDS)).toBe(false); // open, but amount is null
  });

  it('OR requires at least one condition', () => {
    const g = group('or', [cond('status', 'eq', 'closed'), cond('amount', 'gt', 100)]);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true); // amount 120 > 100
    expect(evaluateFilterGroup(g, row('2'), FIELDS)).toBe(true); // status closed
    expect(evaluateFilterGroup(g, row('3'), FIELDS)).toBe(false); // neither
  });
});

describe('evaluateFilterGroup - nested groups, three deep', () => {
  it('recurses through group-in-group-in-group', () => {
    // (status = open) AND ( (amount > 100) OR ( (title contains "thing") AND (amount is_empty) ) )
    const g = group('and', [
      cond('status', 'eq', 'open'),
      group('or', [
        cond('amount', 'gt', 100),
        group('and', [cond('title', 'contains', 'thing'), cond('amount', 'is_empty', true)]),
      ]),
    ]);

    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true); // open, amount 120 > 100
    expect(evaluateFilterGroup(g, row('2'), FIELDS)).toBe(false); // not open at all
    expect(evaluateFilterGroup(g, row('3'), FIELDS)).toBe(true); // open, "Gamma thing" + amount empty
  });

  it('a fourth level still recurses correctly', () => {
    const g = group('and', [
      group('and', [
        group('and', [
          group('or', [cond('title', 'eq', 'Alpha widget'), cond('title', 'eq', 'Beta gadget')]),
        ]),
      ]),
    ]);
    expect(evaluateFilterGroup(g, row('1'), FIELDS)).toBe(true);
    expect(evaluateFilterGroup(g, row('3'), FIELDS)).toBe(false);
  });
});

describe('countFilterConditions', () => {
  it('counts leaves recursively, not groups', () => {
    const g = group('and', [
      cond('status', 'eq', 'open'),
      group('or', [cond('amount', 'gt', 1), cond('amount', 'lt', 1)]),
    ]);
    expect(countFilterConditions(g)).toBe(3);
  });

  it('is zero for null or empty', () => {
    expect(countFilterConditions(null)).toBe(0);
    expect(countFilterConditions(emptyFilterGroup())).toBe(0);
  });
});

describe('operatorsFor / defaultOperatorsFor / newConditionFor', () => {
  it('a field with no declared operators falls back to a sane default for its type', () => {
    expect(operatorsFor(FIELDS[0])).toEqual(defaultOperatorsFor('text'));
    expect(operatorsFor(FIELDS[1])).toEqual(defaultOperatorsFor('select'));
    expect(operatorsFor(FIELDS[2])).toEqual(defaultOperatorsFor('number'));
  });

  it('a field that declares its own operators is not overridden', () => {
    const narrowed: FilterFieldDescriptor<Row> = { ...FIELDS[2], operators: ['gt', 'lt'] };
    expect(operatorsFor(narrowed)).toEqual(['gt', 'lt']);
  });

  it('a fresh condition defaults to the field first operator, is_empty starts true', () => {
    expect(newConditionFor(FIELDS[0])).toEqual({ field_key: 'title', op: 'contains', value: undefined });
    const isEmptyOnly: FilterFieldDescriptor<Row> = { ...FIELDS[0], operators: ['is_empty'] };
    expect(newConditionFor(isEmptyOnly)).toEqual({ field_key: 'title', op: 'is_empty', value: true });
  });
});

describe('describeFilterGroup', () => {
  it('describes a null/empty group as null', () => {
    expect(describeFilterGroup(null, FIELDS)).toBeNull();
    expect(describeFilterGroup(emptyFilterGroup(), FIELDS)).toBeNull();
  });

  it('names the field label, not the field key', () => {
    const g = group('and', [cond('status', 'eq', 'open')]);
    expect(describeFilterGroup(g, FIELDS)).toBe('Status equals open');
  });

  it('joins siblings with the group operator and parenthesises a multi-condition group', () => {
    const g = group('or', [cond('status', 'eq', 'open'), cond('amount', 'gt', 100)]);
    expect(describeFilterGroup(g, FIELDS)).toBe('(Status equals open or Amount greater than 100)');
  });
});

/**
 * RuleBuilder component tests.
 *
 * useRuleFacts is mocked to drive loading / error / empty / data states.
 * The searchable dropdowns + tooltip are stubbed as native controls so fact /
 * operator / value changes are deterministic in jsdom (Radix comboboxes need
 * pointer capture jsdom lacks).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import type { RuleFactItem, RuleGroup } from './types';

// ---- mock the facts hook ----
const useRuleFactsMock = vi.fn();
vi.mock('./useRuleFacts', () => ({
  useRuleFacts: (...a: unknown[]) => useRuleFactsMock(...a),
}));

// ---- stub the searchable dropdowns as native <select> / checkbox groups ----
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    disabled,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
    disabled?: boolean;
  }) => (
    <select
      aria-label={placeholder}
      data-testid={`select-${placeholder}`}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <div data-testid={`multi-${placeholder}`}>
      {(options ?? []).map((o) => (
        <button
          key={o.value}
          type="button"
          data-testid={`multi-opt-${o.value}`}
          onClick={() =>
            onChange(
              value.includes(o.value)
                ? value.filter((x) => x !== o.value)
                : [...value, o.value],
            )
          }
        >
          {o.label}
        </button>
      ))}
    </div>
  ),
}));
vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import { RuleBuilder } from './RuleBuilder';

const FACTS: RuleFactItem[] = [
  {
    key: 'promotion.name',
    label: 'Promotion name',
    type: 'string',
    operators: ['eq', 'neq', 'contains', 'in', 'not_in'],
    source: 'promotion',
    sourceLabel: 'Promotion',
  },
  {
    key: 'promotion.accessLevels',
    label: 'Access levels',
    type: 'list',
    operators: ['contains_any', 'contains_all', 'not_contains'],
    source: 'promotion',
    sourceLabel: 'Promotion',
    options: [
      { value: 'sorento_dealer', label: 'Sorento Dealer' },
      { value: 'cabana_office', label: 'Cabana Office' },
    ],
  },
  {
    key: 'promotion.isActive',
    label: 'Active',
    type: 'boolean',
    operators: ['is_true', 'is_false'],
    source: 'promotion',
    sourceLabel: 'Promotion',
  },
  {
    key: 'promotion.startDate',
    label: 'Start date',
    type: 'date',
    operators: ['before', 'after', 'between'],
    source: 'promotion',
    sourceLabel: 'Promotion',
  },
  {
    key: 'promotion.endDate.daysUntil',
    label: 'Days until end',
    type: 'number',
    operators: ['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'between'],
    source: 'promotion',
    sourceLabel: 'Promotion',
  },
];

function dataState() {
  useRuleFactsMock.mockReturnValue({
    data: FACTS,
    isLoading: false,
    isError: false,
    error: null,
  });
}

beforeEach(() => vi.clearAllMocks());

describe('RuleBuilder - fetch states', () => {
  it('renders null when there are no sources', () => {
    dataState();
    const { container } = render(
      <RuleBuilder sources={[]} value={null} onChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows a loading state', () => {
    useRuleFactsMock.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    expect(screen.getByText(/Loading fields/i)).toBeInTheDocument();
  });

  it('shows an error state', () => {
    useRuleFactsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('boom'),
    });
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('shows an empty-facts state', () => {
    useRuleFactsMock.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    expect(screen.getByText(/no filterable fields/i)).toBeInTheDocument();
  });
});

describe('RuleBuilder - editing', () => {
  it('empty root renders the always-matches hint and Add buttons', () => {
    dataState();
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    expect(screen.getByText(/always matches/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add condition/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add group/i })).toBeInTheDocument();
  });

  it('adding a condition emits a valid tree seeded with the first fact/operator', () => {
    dataState();
    const onChange = vi.fn();
    render(<RuleBuilder sources={['promotion']} value={null} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));

    const tree = onChange.mock.calls.at(-1)![0] as RuleGroup;
    expect(tree.combinator).toBe('and');
    expect(tree.rules).toHaveLength(1);
    expect(tree.rules[0]).toMatchObject({
      kind: 'condition',
      fact: 'promotion.name',
      operator: 'eq',
      valueKind: 'literal',
    });
  });

  it('removing the only condition emits null', () => {
    dataState();
    const onChange = vi.fn();
    render(<RuleBuilder sources={['promotion']} value={null} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));
    fireEvent.click(screen.getByRole('button', { name: /remove condition/i }));
    expect(onChange.mock.calls.at(-1)![0]).toBeNull();
  });

  it('operator options narrow to the selected fact type', () => {
    dataState();
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));

    // string fact → string operators
    let opSelect = screen.getByTestId('select-Operator') as HTMLSelectElement;
    let opValues = Array.from(opSelect.options).map((o) => o.value);
    expect(opValues).toEqual(['eq', 'neq', 'contains', 'in', 'not_in']);

    // switch the field to the list fact → list operators only
    fireEvent.change(screen.getByTestId('select-Field'), {
      target: { value: 'promotion.accessLevels' },
    });
    opSelect = screen.getByTestId('select-Operator') as HTMLSelectElement;
    opValues = Array.from(opSelect.options).map((o) => o.value);
    expect(opValues).toEqual(['contains_any', 'contains_all', 'not_contains']);
  });

  it('cross-fact toggle appears only for scalar operators', () => {
    dataState();
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));

    // default op 'eq' is scalar/crossable → the compare-to-field toggle shows
    expect(screen.getByRole('button', { name: /compare to field/i })).toBeInTheDocument();

    // switch to 'contains' (not a cross-fact operator) → toggle disappears
    fireEvent.change(screen.getByTestId('select-Operator'), {
      target: { value: 'contains' },
    });
    expect(screen.queryByRole('button', { name: /compare to field/i })).toBeNull();
  });

  it('boolean operator renders no value input', () => {
    dataState();
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));
    fireEvent.change(screen.getByTestId('select-Field'), {
      target: { value: 'promotion.isActive' },
    });
    // no free-text/number/date value input for a boolean is_true/is_false
    expect(screen.queryByPlaceholderText('Value')).toBeNull();
  });

  it('between renders two value inputs', () => {
    dataState();
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));
    fireEvent.change(screen.getByTestId('select-Field'), {
      target: { value: 'promotion.endDate.daysUntil' },
    });
    fireEvent.change(screen.getByTestId('select-Operator'), {
      target: { value: 'between' },
    });
    const numberInputs = document.querySelectorAll('input[type="number"]');
    expect(numberInputs.length).toBe(2);
  });

  it('list operator with options renders the multi-select widget', () => {
    dataState();
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));
    fireEvent.change(screen.getByTestId('select-Field'), {
      target: { value: 'promotion.accessLevels' },
    });
    // operator defaults to contains_any (multi shape) → the options widget shows
    expect(screen.getByTestId('multi-opt-sorento_dealer')).toBeInTheDocument();
    expect(screen.getByTestId('multi-opt-cabana_office')).toBeInTheDocument();
  });

  it('adding a nested group creates a child group with its own condition', () => {
    dataState();
    render(<RuleBuilder sources={['promotion']} value={null} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /add group/i }));
    // root + child group → two "Add condition" buttons now.
    expect(screen.getAllByRole('button', { name: /add condition/i }).length).toBe(2);
  });

  it('hides "Add group" once nesting reaches the depth cap (depth 5)', () => {
    dataState();
    const cond = {
      kind: 'condition' as const,
      fact: 'promotion.name',
      operator: 'eq' as const,
      valueKind: 'literal' as const,
      value: 'x',
    };
    // Linear chain nested to depth 5: root(0) -> g1 -> g2 -> g3 -> g4(leaf).
    const group = (rules: unknown[]): RuleGroup =>
      ({ kind: 'group', combinator: 'and', rules } as RuleGroup);
    const value = group([group([group([group([group([cond])])])])]);

    render(<RuleBuilder sources={['promotion']} value={value} onChange={vi.fn()} />);
    // Groups at depth 0..3 still offer "Add group" (depth < RULE_MAX_DEPTH-1 = 4);
    // the depth-4 group does NOT - so exactly 4 "Add group" buttons.
    expect(screen.getAllByRole('button', { name: /add group/i }).length).toBe(4);
  });

  it('still offers "Add group" for a shallow (depth 1) tree', () => {
    dataState();
    const value: RuleGroup = {
      kind: 'group',
      combinator: 'and',
      rules: [
        {
          kind: 'group',
          combinator: 'and',
          rules: [
            {
              kind: 'condition',
              fact: 'promotion.name',
              operator: 'eq',
              valueKind: 'literal',
              value: 'x',
            },
          ],
        },
      ],
    };
    render(<RuleBuilder sources={['promotion']} value={value} onChange={vi.fn()} />);
    // root (depth 0) + child group (depth 1) both under the cap → 2 buttons.
    expect(screen.getAllByRole('button', { name: /add group/i }).length).toBe(2);
  });

  it('seeds the draft from an initial value tree', () => {
    dataState();
    const value: RuleGroup = {
      kind: 'group',
      combinator: 'or',
      rules: [
        {
          kind: 'condition',
          fact: 'promotion.name',
          operator: 'contains',
          valueKind: 'literal',
          value: 'Sorento',
        },
      ],
    };
    render(<RuleBuilder sources={['promotion']} value={value} onChange={vi.fn()} />);
    const opSelect = screen.getByTestId('select-Operator') as HTMLSelectElement;
    expect(opSelect.value).toBe('contains');
    const valInput = screen.getByPlaceholderText('Value') as HTMLInputElement;
    expect(valInput.value).toBe('Sorento');
  });
});

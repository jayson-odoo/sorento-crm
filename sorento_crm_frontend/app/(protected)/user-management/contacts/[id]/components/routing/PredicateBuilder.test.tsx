import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PredicateBuilder } from './PredicateBuilder';
import {
  operatorsForFieldType,
  fieldUsesOptionValue,
  isWildcard,
  type Predicate,
  type RoutableField,
} from './predicateTypes';

const FIELDS: RoutableField[] = [
  {
    field: 'sales_type',
    label: 'Sales Type',
    type: 'lookup',
    options: [
      { value: 'project', label: 'Project' },
      { value: 'cash_sales', label: 'Cash Sales' },
    ],
  },
  { field: 'customer_name', label: 'Customer Name', type: 'string' },
  { field: 'total_project_value', label: 'Total Project Value', type: 'numeric' },
];

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('predicate helpers', () => {
  it('hides contains/not_contains for enum, numeric and lookup fields', () => {
    expect(operatorsForFieldType('string').map((o) => o.value)).toEqual([
      'equals',
      'not_equals',
      'contains',
      'not_contains',
    ]);
    for (const t of ['lookup', 'enum', 'numeric'] as const) {
      expect(operatorsForFieldType(t).map((o) => o.value)).toEqual([
        'equals',
        'not_equals',
      ]);
    }
  });

  it('uses an option dropdown value only for lookup/enum fields', () => {
    expect(fieldUsesOptionValue('lookup')).toBe(true);
    expect(fieldUsesOptionValue('enum')).toBe(true);
    expect(fieldUsesOptionValue('numeric')).toBe(false);
    expect(fieldUsesOptionValue('string')).toBe(false);
  });

  it('treats an empty predicate list as a wildcard', () => {
    expect(isWildcard([])).toBe(true);
    expect(isWildcard([{ field: 'x', operator: 'equals', value: 'y' }])).toBe(false);
  });
});

describe('PredicateBuilder', () => {
  it('shows a wildcard message when there are no predicates', () => {
    render(<PredicateBuilder predicates={[]} fields={FIELDS} onChange={vi.fn()} />);
    expect(screen.getByText(/matches/i)).toBeInTheDocument();
    expect(screen.getByText(/wildcard/i)).toBeInTheDocument();
  });

  it('appends a new predicate when "Add condition" is clicked', () => {
    const onChange = vi.fn();
    render(<PredicateBuilder predicates={[]} fields={FIELDS} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as Predicate[];
    expect(next).toHaveLength(1);
    expect(next[0].field).toBe('sales_type'); // first field
    expect(next[0].operator).toBe('equals');
  });

  it('renders a text input value for a string field', () => {
    const predicates: Predicate[] = [
      { field: 'customer_name', operator: 'contains', value: 'Acme' },
    ];
    render(<PredicateBuilder predicates={predicates} fields={FIELDS} onChange={vi.fn()} />);
    const input = screen.getByLabelText('Predicate value') as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.type).toBe('text');
    expect(input.value).toBe('Acme');
  });

  it('renders a number input for a numeric field', () => {
    const predicates: Predicate[] = [
      { field: 'total_project_value', operator: 'equals', value: '1000' },
    ];
    render(<PredicateBuilder predicates={predicates} fields={FIELDS} onChange={vi.fn()} />);
    const input = screen.getByLabelText('Predicate value') as HTMLInputElement;
    expect(input.type).toBe('number');
  });

  it('renders an option dropdown (not a text input) for a lookup field', () => {
    const predicates: Predicate[] = [
      { field: 'sales_type', operator: 'equals', value: 'project' },
    ];
    render(<PredicateBuilder predicates={predicates} fields={FIELDS} onChange={vi.fn()} />);
    // Lookup value uses SearchableSelect — no free-text input.
    expect(screen.queryByLabelText('Predicate value')).not.toBeInTheDocument();
    expect(screen.getByTestId('predicate-row')).toBeInTheDocument();
  });

  it('removes a predicate when the remove button is clicked', () => {
    const onChange = vi.fn();
    const predicates: Predicate[] = [
      { field: 'customer_name', operator: 'equals', value: 'A' },
      { field: 'total_project_value', operator: 'equals', value: '1' },
    ];
    render(<PredicateBuilder predicates={predicates} fields={FIELDS} onChange={onChange} />);
    fireEvent.click(screen.getAllByRole('button', { name: /remove condition/i })[0]);
    const next = onChange.mock.calls[0][0] as Predicate[];
    expect(next).toHaveLength(1);
    expect(next[0].field).toBe('total_project_value');
  });
});

/**
 * The set explosion, which is the thing a naive line list gets wrong.
 *
 * The PO says "927 SETS"; the sales order says a priced parent plus its zero-priced
 * companions. 52 PO lines become 99 sales order lines that way, so the table has to let a
 * person read a set AS a set instead of nine unrelated rows.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  ProjectSalesOrderFinding,
  ProjectSalesOrderLine,
} from '../../_shared/types/projectSalesOrder.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { SalesOrderLinesTable, groupExplodedLines } from './SalesOrderLinesTable';

function line(overrides: Partial<ProjectSalesOrderLine>): ProjectSalesOrderLine {
  return {
    id: overrides.id ?? 'l1',
    line_no: overrides.line_no ?? 1,
    product_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    qty: '600',
    uom: 'UNIT',
    unit_price: '11.16000',
    amount: '6696.00',
    delivery_date: '2026-07-01',
    phase_label: 'Level 2 & 7',
    explosion_source: 'none',
    source_po_line_no: 1,
    stock_location: 'BRW-BB',
    ...overrides,
  };
}

/** One WC set: a priced pedestal plus three zero-priced companions, from PO line 10. */
const SET_LINES: ProjectSalesOrderLine[] = [
  line({
    id: 'parent',
    line_no: 5,
    product_code: 'SRTWCX8608-RL',
    description: 'SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)',
    qty: '124',
    uom: 'SET',
    unit_price: '305.55000',
    amount: '37888.20',
    explosion_source: 'package',
    source_po_line_no: 10,
  }),
  line({
    id: 'cistern',
    line_no: 6,
    product_code: 'SRTWCY8608',
    description: 'SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP)',
    qty: '124',
    unit_price: '0.00000',
    amount: '0.00',
    explosion_source: 'package',
    source_po_line_no: 10,
  }),
  line({
    id: 'seat',
    line_no: 7,
    product_code: 'SRTWC8608-SC',
    description: 'SORENTO SRTWC8608-SC SEAT COVER ONLY',
    qty: '124',
    unit_price: '0.00000',
    amount: '0.00',
    explosion_source: 'package',
    source_po_line_no: 10,
  }),
  line({
    id: 'connector',
    line_no: 8,
    product_code: 'TPE-9300',
    description: 'FLEXIBLE STRAIGHT CONNECTOR P10 B (4")100MM',
    qty: '124',
    unit_price: '0.00000',
    amount: '0.00',
    explosion_source: 'package',
    source_po_line_no: 10,
  }),
];

function renderTable(props: Partial<React.ComponentProps<typeof SalesOrderLinesTable>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrderLinesTable lines={SET_LINES} {...props} />
    </QueryClientProvider>,
  );
}

describe('groupExplodedLines', () => {
  it('hangs the zero-priced companions under the priced parent of their PO line', () => {
    const groups = groupExplodedLines(SET_LINES);

    expect(groups).toHaveLength(1);
    expect(groups[0].parent.product_code).toBe('SRTWCX8608-RL');
    expect(groups[0].companions.map((companion) => companion.product_code)).toEqual([
      'SRTWCY8608',
      'SRTWC8608-SC',
      'TPE-9300',
    ]);
  });

  it('promotes the priced line even when a companion is listed first', () => {
    const groups = groupExplodedLines([SET_LINES[1], SET_LINES[0]]);

    expect(groups).toHaveLength(1);
    expect(groups[0].parent.product_code).toBe('SRTWCX8608-RL');
    expect(groups[0].companions.map((companion) => companion.id)).toEqual(['cistern']);
  });

  it('leaves lines with no source PO line standing alone, never lumped together', () => {
    const groups = groupExplodedLines([
      line({ id: 'a', line_no: 1, source_po_line_no: null }),
      line({ id: 'b', line_no: 2, source_po_line_no: null }),
    ]);

    expect(groups).toHaveLength(2);
    expect(groups.every((group) => group.companions.length === 0)).toBe(true);
  });
});

describe('SalesOrderLinesTable', () => {
  it('labels the set and shows its components under the parent', () => {
    renderTable();

    expect(screen.getByText('Set from PO line 10: 4 components')).toBeInTheDocument();
    expect(screen.getByText('SRTWCX8608-RL')).toBeInTheDocument();
    expect(screen.getByText('SRTWCY8608')).toBeInTheDocument();
    expect(screen.getAllByLabelText('Companion of the line above')).toHaveLength(3);
    expect(screen.getByText('4 lines, 1 set exploded')).toBeInTheDocument();
  });

  it('collapses a set to its parent and opens it again', () => {
    renderTable();

    const toggle = screen.getByRole('button', { name: /Set from PO line 10/ });
    fireEvent.click(toggle);

    expect(screen.getByText('SRTWCX8608-RL')).toBeInTheDocument();
    expect(screen.queryByText('SRTWCY8608')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Set from PO line 10/ }));
    expect(screen.getByText('SRTWCY8608')).toBeInTheDocument();
  });

  it('narrows to the set a finding concerns, and back again', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    const other = line({
      id: 'other',
      line_no: 1,
      product_code: 'CB6645-NL',
      source_po_line_no: 3,
    });
    const onClear = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <SalesOrderLinesTable
          lines={[other, ...SET_LINES]}
          focusLineId="seat"
          onClearFocus={onClear}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByText('SRTWCX8608-RL')).toBeInTheDocument();
    expect(screen.queryByText('CB6645-NL')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Show all lines' }));
    expect(onClear).toHaveBeenCalled();
  });

  it('marks the line a blocking finding sits on', () => {
    const findings: ProjectSalesOrderFinding[] = [
      {
        id: 'f1',
        severity: 'hard',
        code: 'line_arithmetic',
        detail: 'Line 5: 124 x 305.55 is 37,888.20 but the PO says 37,880.20.',
        line_id: 'parent',
        line_no: 5,
      },
    ];

    renderTable({ findings });

    const row = screen.getByText('SRTWCX8608-RL').closest('tr') as HTMLElement;
    expect(within(row).getByText('Blocking')).toBeInTheDocument();
  });

  it('says a draft with no lines has none instead of rendering an empty grid', () => {
    renderTable({ lines: [] });

    expect(screen.getByText('This draft has no lines')).toBeInTheDocument();
  });
});

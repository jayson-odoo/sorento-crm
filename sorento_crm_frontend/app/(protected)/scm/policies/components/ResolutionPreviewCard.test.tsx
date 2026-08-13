/**
 * ResolutionPreviewCard - empty / winner+chain / global-wins note / error.
 *   AC-PREV-1 (winner + resolution chain render),
 *   AC-PREV-3 (no cell/class match → global wins with an explanatory note, not an error),
 *   AC-STD-4 (empty state before the first run).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

const hooks = vi.hoisted(() => ({
  useProductScopeOptions: vi.fn(),
  useWarehouseScopeOptions: vi.fn(),
  useResolvePolicy: vi.fn(),
}));
vi.mock('../hooks/usePolicies', () => hooks);

// SearchableSelect → native select (the pickers aren't exercised here, but the
// real popover needs DOM APIs jsdom lacks).
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select aria-label={placeholder ?? 'select'} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder ?? ''}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { ResolutionPreviewCard } from './ResolutionPreviewCard';
import type { ReorderPolicyRow, ResolutionResult } from '../types/policy.types';

function policy(over: Partial<ReorderPolicyRow>): ReorderPolicyRow {
  return {
    id: 'pol-1',
    scope_type: 'global',
    scope_ref: null,
    scope_label: '-',
    policy_type: 'reorder_point',
    service_level: null,
    safety_stock_method: 'fixed_days',
    safety_days: 7,
    review_period_days: null,
    forecast_window_days: 90,
    baseline_source: null,
    spike_handling: null,
    buy_scope: null,
    dead_stock_days: 180,
    overstock_days: 120,
    min_override: null,
    max_override: null,
    priority: 0,
    is_active: true,
    supplier_selection: 'best_score',
    lead_time_default_days: 14,
    ...over,
  };
}

/** A SKU-wins result: the SKU override is the winner over the global default. */
const SKU_WINS: ResolutionResult = {
  product: { product_code: 'BRK-450', product_name: 'Brake Disc 450mm' },
  warehouse: null,
  abc_xyz_cell: 'A-X',
  product_class: 'BRK',
  winner: policy({ id: 'pol-sku', scope_type: 'sku', scope_ref: 'prd-1', scope_label: 'BRK-450 · Brake Disc 450mm', policy_type: 'min_max', min_override: 40, max_override: 200 }),
  chain: [
    { scope_type: 'sku', scope_ref: 'prd-1', scope_label: 'BRK-450 · Brake Disc 450mm', matched: true, is_winner: true, reason: 'most-specific-active' },
    { scope_type: 'abc_xyz_cell', scope_ref: 'A-X', scope_label: 'A·X', matched: true, is_winner: false, reason: 'most-specific-active' },
    { scope_type: 'product_class', scope_ref: 'BRK', scope_label: 'Braking', matched: true, is_winner: false, reason: 'most-specific-active' },
    { scope_type: 'global', scope_ref: null, scope_label: 'Global default', matched: true, is_winner: false, reason: 'most-specific-active' },
  ],
};

/** No cell / class / sku override → global default wins (AC-PREV-3). */
const GLOBAL_WINS: ResolutionResult = {
  product: { product_code: 'SPK-010', product_name: 'Spark Plug 010' },
  warehouse: null,
  abc_xyz_cell: null,
  product_class: 'ELE',
  winner: policy({ id: 'pol-global', scope_type: 'global', scope_label: '-' }),
  chain: [
    { scope_type: 'sku', scope_ref: 'prd-5', scope_label: 'SPK-010 · Spark Plug 010', matched: false, is_winner: false, reason: 'no-match' },
    { scope_type: 'abc_xyz_cell', scope_ref: null, scope_label: 'No ABC-XYZ class', matched: false, is_winner: false, reason: 'no-match' },
    { scope_type: 'product_class', scope_ref: 'ELE', scope_label: 'Electrical', matched: false, is_winner: false, reason: 'no-match' },
    { scope_type: 'global', scope_ref: null, scope_label: 'Global default', matched: true, is_winner: true, reason: 'most-specific-active' },
  ],
};

function mockResolve(over: Record<string, unknown>) {
  hooks.useResolvePolicy.mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    error: null,
    mutate: vi.fn(),
    ...over,
  });
}

beforeEach(() => {
  hooks.useProductScopeOptions.mockReturnValue({ data: [{ value: 'prd-1', label: 'BRK-450 · Brake Disc' }], isLoading: false });
  hooks.useWarehouseScopeOptions.mockReturnValue({ data: [], isLoading: false });
  hooks.useResolvePolicy.mockReset();
});

describe('ResolutionPreviewCard', () => {
  it('shows the empty prompt before the first run (AC-STD-4)', () => {
    mockResolve({});
    render(<ResolutionPreviewCard />);
    expect(screen.getByText(/select Resolve to preview the winning policy/i)).toBeInTheDocument();
  });

  it('renders the error state (never crashes)', () => {
    mockResolve({ isError: true, error: new Error('Product not found') });
    render(<ResolutionPreviewCard />);
    expect(screen.getByText('Product not found')).toBeInTheDocument();
  });

  it('renders the winner + full resolution chain (AC-PREV-1)', () => {
    mockResolve({ data: SKU_WINS });
    render(<ResolutionPreviewCard />);
    // Winner badge + effective-values header.
    expect(screen.getByText('Winner')).toBeInTheDocument();
    expect(screen.getByText('Effective policy values')).toBeInTheDocument();
    // All four scope rungs appear in the chain.
    expect(screen.getAllByText('SKU').length).toBeGreaterThan(0);
    expect(screen.getByText('ABC-XYZ cell')).toBeInTheDocument();
    expect(screen.getByText('Product class')).toBeInTheDocument();
    expect(screen.getAllByText('Global default').length).toBeGreaterThan(0);
    // Product identity renders (no UUID).
    expect(screen.getByText('BRK-450')).toBeInTheDocument();
  });

  it('renders the global-wins explanatory note, not an error (AC-PREV-3)', () => {
    mockResolve({ data: GLOBAL_WINS });
    render(<ResolutionPreviewCard />);
    expect(
      screen.getByText(/no matching SKU, ABC-XYZ cell, or product-class override/i),
    ).toBeInTheDocument();
    // The "no ABC-XYZ class" case is shown as a badge/label, not an error.
    expect(screen.getAllByText('No ABC-XYZ class').length).toBeGreaterThan(0);
    // Winner is the global default and it is flagged as the winner.
    expect(screen.getByText('Winner')).toBeInTheDocument();
  });
});

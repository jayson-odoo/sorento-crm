/**
 * AC-S8.1 (PLAN-reorder-feedback-9sep.md, S8 / G4 ruling 9 Sep 2026): the Product health
 * radio preselects from the health class when nothing is stored yet - Dead -> Discontinue,
 * everything else -> Keep selling - and a STORED lifecycle decision always wins over the
 * suggestion. Before the fix (`PlanRowPanel.tsx`'s `lifecycle` value, currently
 * `edit?.lifecycle ?? economics?.lifecycle_decision ?? null`) an undecided Dead product's
 * radio group sits with NEITHER option selected.
 *
 * Render harness copied read-only from `PlanRowPanel.test.tsx` (fixtures + mocks) - this
 * file adds no new mocks, it only exercises the default-selection behaviour.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import { NO_COVER } from '../lib/coverPlan';
import type { ProductEconomics } from '../lib/productHealth';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

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
    options: { value: string; label: string; description?: string }[];
    placeholder?: string;
    disabled?: boolean;
  }) => (
    <select
      aria-label={placeholder ?? 'Supplier'}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.description ? `${o.label} - ${o.description}` : o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('react-apexcharts', () => ({ default: () => <div data-testid="chart-stub" /> }));

import { PlanRowPanel } from './PlanRowPanel';

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 23, recommended_qty: 23, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -23, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10, currency: 'MYR',
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: 10, master_moq: 10, moq_is_override: false,
    order_multiple: 25, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 230, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 4, outstanding_po: 0, outstanding_sales: 24,
    project_committed: 0, retail_committed: 24,
    segment: 'dealer',
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

function renderPanel(over: Partial<React.ComponentProps<typeof PlanRowPanel>> = {}) {
  const onEdit = vi.fn();
  const onUseSuggestion = vi.fn();
  const props: React.ComponentProps<typeof PlanRowPanel> = {
    line: line(),
    edit: undefined,
    decision: undefined,
    cover: NO_COVER,
    poReceipts: [],
    price: undefined,
    levelSuggestion: undefined,
    economics: undefined,
    onEdit,
    onUseSuggestion,
    ...over,
  };
  render(<PlanRowPanel {...props} />);
  return { onEdit, onUseSuggestion };
}

const economics = (over: Partial<ProductEconomics> = {}): ProductEconomics => ({
  product_id: 'p1', avg_sell_price: 20, sell_source: 'orders', sold_qty: 30, on_hand: 5,
  avg_monthly_out: 10, turnover_months: 0.5, no_movement: false, lifecycle_decision: null,
  lifecycle_decided_at: null, sold_recent_qty: 12, bought_recent_qty: 20,
  movement_class: 'fast_moving',
  ...over,
});

describe('PlanRowPanel - Product health default selection (AC-S8.1)', () => {
  it('a dead product with no stored decision preselects Discontinue', () => {
    renderPanel({ economics: economics({ movement_class: 'dead' }) });
    expect(screen.getByRole('radio', { name: 'Discontinue' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Keep selling' })).not.toBeChecked();
  });

  it('a slow_moving product with no stored decision preselects Keep selling', () => {
    renderPanel({ economics: economics({ movement_class: 'slow_moving' }) });
    expect(screen.getByRole('radio', { name: 'Keep selling' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Discontinue' })).not.toBeChecked();
  });

  it('a stored "keep" decision on a DEAD product wins over the discontinue suggestion', () => {
    renderPanel({
      economics: economics({ movement_class: 'dead', lifecycle_decision: 'keep' }),
    });
    expect(screen.getByRole('radio', { name: 'Keep selling' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Discontinue' })).not.toBeChecked();
  });
});

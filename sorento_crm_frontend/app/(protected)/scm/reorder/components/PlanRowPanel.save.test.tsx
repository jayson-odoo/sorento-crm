/**
 * AC-S12.1/AC-S13.2 (round 2, reorder-feedback-9sep): the row's "Use suggestion" button
 * becomes "Save" - it persists THIS ROW immediately (`usePlanEdits.saveRow`, its own suite
 * in `hooks/usePlanEdits.test.tsx`); "Skip" is unchanged. The MOQ input prefills from the
 * remembered product-supplier link (`rec.supplier.moq`) when nothing else names one.
 *
 * Harness copied from `PlanRowPanel.test.tsx` (read-only) - same `SearchableSelect` /
 * `react-apexcharts` stand-ins and the same `rec()`/`line()` fixture builders.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import { NO_COVER } from '../lib/coverPlan';

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
    supplier: {
      supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10, currency: 'MYR',
      lead_time_days: 30, composite_score: 0, is_primary: true, moq: 100,
    },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    // No frozen master/override MOQ of its own - AC-S13.2's prefill has to come from
    // `rec.supplier.moq` (the remembered product-supplier link) in this case.
    moq: null, master_moq: null, moq_is_override: false,
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
  const onSave = vi.fn();
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
    onSave,
    ...over,
  };
  render(<PlanRowPanel {...props} />);
  return { onEdit, onSave };
}

describe('PlanRowPanel row Save (AC-S12.1)', () => {
  it('reads "Save", not "Use suggestion", and clicking it calls onSave', () => {
    const { onSave } = renderPanel();
    expect(screen.queryByRole('button', { name: 'Use suggestion' })).not.toBeInTheDocument();
    const saveButton = screen.getByRole('button', { name: 'Save' });
    fireEvent.click(saveButton);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('still renders Skip alongside Save', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: 'Skip' })).toBeInTheDocument();
  });
});

/**
 * AC-S12.5 (round 2, reorder-feedback-9sep, review fix round 3): a Buy value typed but not
 * yet blurred lives only in the panel's own `buyDraft` state - `onEdit` never ran, so the
 * shared draft the toolbar's Save (N) reads has nothing in it. Row Save must not depend on
 * blur having already happened: it computes the same patch `commitBuy`'s blur would have
 * applied and passes it straight to `onSave` as a second argument, so the very save about
 * to fire carries it. The merge itself (`usePlanEdits.saveRow`) has its own suite in
 * `hooks/usePlanEdits.test.tsx`; this only proves the panel COMPUTES and SENDS the patch.
 */
describe('PlanRowPanel row Save flushes an un-blurred Buy value (AC-S12.5)', () => {
  it('typing into Buy and clicking Save WITHOUT blurring calls onSave with a patch carrying buy 25', () => {
    // order_qty 40 with no MOQ + order_multiple 25 suggests a default Buy of 50 (ceil to
    // the multiple) - a DIFFERENT figure from what is typed below, so this proves the
    // typed 25 actually landed rather than coincidentally matching what was already
    // showing (React's own change-tracking treats a same-value fireEvent.change as a
    // no-op, which the default fixture's own suggested Buy of 25 would have masked).
    const { onSave } = renderPanel({ line: line({ order_qty: 40 }) });
    const buyInput = screen.getByLabelText('Units to buy') as HTMLInputElement;
    expect(buyInput.value).toBe('50');

    fireEvent.change(buyInput, { target: { value: '25' } });
    // No fireEvent.blur(buyInput) here - Save must not depend on it.
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ decision: expect.objectContaining({ buy: 25 }) }),
    );
  });

  it('clicking Save with no draft and no pending input calls onSave with undefined', () => {
    const { onSave } = renderPanel();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(undefined);
  });
});

describe('PlanRowPanel MOQ prefill from the remembered supplier link (AC-S13.2)', () => {
  it('with no edit and no moq_override, the MOQ input value is rec.supplier.moq', () => {
    renderPanel();
    const moqInput = screen.getByLabelText('MOQ') as HTMLInputElement;
    expect(moqInput.value).toBe('100');
  });
});

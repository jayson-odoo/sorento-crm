/**
 * AC-S11.1/AC-S11.2/AC-S11.3/AC-S11.4 (round 2, reorder-feedback-9sep).
 *
 * Measured: for SRTSS8710 the engine's suggested supplier is the DEFAULT product_suppliers
 * link at MYR 121.80, while the last purchase is CNY 48.00 from KAIPING HANSHUN. The row
 * used to print "Line cost RM 56,271.60 at last price" (462 x 121.80) under the "at last
 * price" label - a stale default's cost, wrongly labelled. This file pins the fix: the
 * supplier select prefills from the LAST PURCHASE supplier (not the engine default), the
 * line cost reads Buy qty x the purchase's own price in the purchase's own currency, and
 * the "No MYR rate" hint (AC-S2.4) is gone.
 *
 * Harness copied from `PlanRowPanel.test.tsx` (read-only) - same `SearchableSelect` /
 * `react-apexcharts` stand-ins and the same `rec()`/`line()` fixture builders.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
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
    id: 'r1', type: 'buy', sku: 'SRTSS8710', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 462, recommended_qty: 462, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -462, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: {
      supplier_code: 'DEFAULT', supplier_name: 'DEFAULT', unit_cost: 121.8, currency: 'MYR',
      lead_time_days: 30, composite_score: 0, is_primary: true,
    },
    alternatives: [
      {
        supplier_code: 'KAIPING', supplier_name: 'KAIPING HANSHUN', unit_cost: 48,
        currency: 'CNY', lead_time_days: 20, composite_score: 0, is_primary: false,
      },
    ],
    is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: 10, master_moq: 10, moq_is_override: false,
    order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 121.8, cash_impact: 56271.6, rank: 1, rank_score: 0, funding_status: null,
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

describe('PlanRowPanel line cost + supplier prefill (round 2, AC-S11.1-S11.4)', () => {
  it('use_last: Line cost is Buy qty x LAST price in the PURCHASE currency, and the select prefills to the last-purchase supplier (AC-S11.1/S11.2)', () => {
    renderPanel({
      // `last_purchase_cost`/`last_purchase_currency`/`last_purchase_supplier_code` are the
      // rec's OWN fields (S11, round 2, 9 Sep) - the true last purchase, independent of the
      // engine's DEFAULT candidate link this row's `supplier`/`alternatives` still name.
      line: line({
        last_purchase_cost: 48,
        last_purchase_currency: 'CNY',
        last_purchase_supplier_code: 'KAIPING',
      }),
      edit: { decision: { buy: 462 }, priceMode: 'use_last' },
    });

    // AC-S11.2: "Line cost CNY 22,176.00 at last price" (462 x 48.00), not the stale
    // MYR 56,271.60 the engine's default link (121.80) used to print.
    expect(screen.getByText('CNY 22,176.00')).toBeInTheDocument();
    expect(screen.getByText('at last price')).toBeInTheDocument();
    expect(screen.queryByText(/56,271\.60/)).not.toBeInTheDocument();

    // AC-S11.1: KAIPING preselected even though the row's own (engine) supplier is DEFAULT.
    const select = screen.getByLabelText('Choose a supplier') as HTMLSelectElement;
    expect(select.value).toBe('KAIPING');

    // AC-S11.3: the "No MYR rate" hint is retired.
    expect(screen.queryByText(/No MYR rate/)).not.toBeInTheDocument();
  });

  it('ask_new: Line cost is Buy qty x the CHOSEN SUPPLIER cost in the supplier currency (AC-S11.2)', () => {
    renderPanel({
      // No last purchase on file for this row - the supplier field falls back to the
      // engine's own chosen supplier (USD1), not a last-purchase prefill.
      line: line({
        unit_cost: 3.5,
        supplier: { supplier_code: 'USD1', supplier_name: 'US Supplier', unit_cost: 3.5, currency: 'USD', lead_time_days: 10, composite_score: 0, is_primary: true },
        alternatives: [],
      }),
      edit: { decision: { buy: 10 }, priceMode: 'ask_new' },
    });

    expect(screen.getByText('USD 35.00')).toBeInTheDocument();
    expect(screen.getByText('at supplier price')).toBeInTheDocument();
    expect(screen.queryByText(/No MYR rate/)).not.toBeInTheDocument();
  });

  it('renders "Line cost -" with neither a last price nor a supplier cost', () => {
    renderPanel({
      line: line({
        unit_cost: null,
        supplier: { supplier_code: '', supplier_name: 'No supplier', unit_cost: null, currency: null, lead_time_days: 0, composite_score: 0, is_primary: false },
        alternatives: [],
      }),
    });
    const lineCostRow = screen.getByText('Line cost').closest('p');
    expect(lineCostRow).not.toBeNull();
    expect(lineCostRow!).toHaveTextContent('Line cost -');
  });
});

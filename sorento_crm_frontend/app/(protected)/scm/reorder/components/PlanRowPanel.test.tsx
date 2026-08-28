/**
 * PlanRowPanel - the whole decision for one product, in the row that asks it
 * (plan 4.4, UAC D1-D9).
 *
 * Every control writes to `onEdit`, the draft map's own setter - nothing here calls a
 * service directly (that is `usePlanEdits`'s job, its own suite). SearchableSelect is
 * mocked to a native `<select>` (Radix popover + cmdk is non-deterministic in jsdom),
 * the same stand-in `AdjustRecommendationModal.test.tsx` already uses.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import { NO_COVER, type CoverProposal } from '../lib/coverPlan';
import type { PoReceipt } from '../lib/poCover';
import type { PriceAdvice, CheaperAlternative } from '../lib/priceAdvice';
import type { LevelSuggestion } from '../lib/levelSuggestion';
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

// react-apexcharts pulls in a canvas-heavy chart the level-chart link opens; the panel
// only needs it to exist behind `dynamic()`, never to actually render a chart in jsdom.
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

// A site pool: after R18 a project bin is never offered as a cover source at all.
const cover: CoverProposal = {
  coverQty: 5,
  buyQty: 18,
  sources: [{ warehouse_id: 'w2', warehouse_code: 'DC1', qty: 5, segment: 'dealer', offered: 5 }],
  offered: [{ warehouse_id: 'w2', warehouse_code: 'DC1', qty: 5 }],
} as unknown as CoverProposal;

/** Two pools between them covering the shortage - what a split take looks like. */
const twoPoolCover: CoverProposal = {
  coverQty: 9,
  buyQty: 14,
  sources: [
    { warehouse_id: 'w2', warehouse_code: 'DC1', qty: 6, segment: 'dealer' },
    { warehouse_id: 'w3', warehouse_code: 'MWH', qty: 3, segment: 'dealer' },
  ],
  offered: [
    { warehouse_id: 'w2', warehouse_code: 'DC1', qty: 6 },
    { warehouse_id: 'w3', warehouse_code: 'MWH', qty: 3 },
  ],
} as unknown as CoverProposal;

const poReceipts: PoReceipt[] = [
  { po_number: 'PO-9', status: 'active', expected_date: '2026-09-01', remaining: 12 },
];

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

describe('PlanRowPanel - four zones render (D1)', () => {
  it('renders Cover, Price and supplier, AutoCount level + qty, Product health', () => {
    renderPanel();
    expect(screen.getByText('Cover')).toBeInTheDocument();
    expect(screen.getByText('Price and supplier')).toBeInTheDocument();
    expect(screen.getByText('AutoCount level + qty')).toBeInTheDocument();
    expect(screen.getByText('Product health')).toBeInTheDocument();
  });
});

describe('PlanRowPanel - Cover zone (D2)', () => {
  it('shows the stock cap, PO cap and SPO fact, and the MOQ master figure beside the input', () => {
    renderPanel({ cover, poReceipts });
    expect(screen.getByText(/pool available 5/)).toBeInTheDocument();
    expect(screen.getByText(/open 12/)).toBeInTheDocument();
    // SPO arriving is a FACT (R2) - text, not an input.
    expect(screen.getByText('already in net')).toBeInTheDocument();
    expect(screen.getByLabelText('Units to buy')).toBeInTheDocument();
    expect(screen.getByText('master 10')).toBeInTheDocument();
  });

  it('SPO arriving reads the recommendation\'s own incoming_spo, never zero by default', () => {
    renderPanel({ line: line({ incoming_spo: 4 }) });
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('shows the over/short hint only when the mixture differs from the suggested quantity', () => {
    // suggestedDecisionFor(line(order_qty:23), NO_COVER, []) -> buy 23 (rounded to moq/multiple);
    // an edited decision of buy:50 is well over that.
    renderPanel({ edit: { decision: { buy: 50 } } });
    expect(screen.getByText(/over suggested/)).toBeInTheDocument();
  });

  it('says nothing about over/short when the mixture equals the suggestion', () => {
    // No MOQ/multiple rounding in play, so the untouched row's own suggestion exactly
    // meets the need - the fixture used elsewhere in this file rounds 23 up to 25 via
    // its MOQ/multiple, which is itself the "over" case covered above.
    renderPanel({ line: line({ moq: null, order_multiple: null }) });
    expect(screen.queryByText(/over suggested/)).not.toBeInTheDocument();
    expect(screen.queryByText(/short of suggested/)).not.toBeInTheDocument();
  });

  it('Use suggestion and Skip write through onEdit/onUseSuggestion, never a direct save', () => {
    const { onEdit, onUseSuggestion } = renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Use suggestion' }));
    expect(onUseSuggestion).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    expect(onEdit).toHaveBeenCalledWith({ decision: { skip: true } });
  });

  it('a skipped row reads its own button as Skipped', () => {
    renderPanel({ edit: { decision: { skip: true } } });
    expect(screen.getByRole('button', { name: 'Skipped' })).toBeInTheDocument();
  });

  it('editing MOQ writes the numeric value to the draft', () => {
    const { onEdit } = renderPanel();
    fireEvent.change(screen.getByLabelText('MOQ'), { target: { value: '40' } });
    expect(onEdit).toHaveBeenCalledWith({ moq: 40 });
  });

  it('clearing MOQ withdraws the override as null, not zero or absent', () => {
    const { onEdit } = renderPanel({ edit: { moq: 40 } });
    fireEvent.change(screen.getByLabelText('MOQ'), { target: { value: '' } });
    expect(onEdit).toHaveBeenCalledWith({ moq: null });
  });

  it('names the pools the From-stock units come out of when there is more than one (R18)', () => {
    renderPanel({ cover: twoPoolCover });
    expect(screen.getByText('DC1 6 + MWH 3')).toBeInTheDocument();
  });

  it('states no split for a single source - the hint already says how many, and where', () => {
    renderPanel({ cover });
    expect(screen.queryByText(/DC1 5/)).not.toBeInTheDocument();
  });

  it('From stock is capped at the pool available quantity, never past it', () => {
    const { onEdit } = renderPanel({ cover });
    fireEvent.change(screen.getByLabelText('From stock'), { target: { value: '999' } });
    const [[patch]] = onEdit.mock.calls;
    expect((patch as { decision: { stock?: { qty: number } } }).decision.stock?.qty).toBeLessThanOrEqual(5);
  });
});

describe('PlanRowPanel - Buy re-rounds to MOQ and multiple on blur (D3)', () => {
  it('typing a value below MOQ rounds up to the nearest multiple past it on blur', () => {
    // moq: 10, order_multiple: 25 - 13 rounds to max(13,10)=13, then ceil(13/25)*25 = 25.
    const { onEdit } = renderPanel();
    const buyInput = screen.getByLabelText('Units to buy');
    fireEvent.change(buyInput, { target: { value: '13' } });
    fireEvent.blur(buyInput);
    expect(onEdit).toHaveBeenCalledWith(
      expect.objectContaining({ decision: expect.objectContaining({ buy: 25 }) }),
    );
  });

  it('Enter commits the same as blur', () => {
    const { onEdit } = renderPanel();
    const buyInput = screen.getByLabelText('Units to buy');
    fireEvent.change(buyInput, { target: { value: '13' } });
    fireEvent.keyDown(buyInput, { key: 'Enter' });
    fireEvent.blur(buyInput);
    expect(onEdit).toHaveBeenCalledWith(
      expect.objectContaining({ decision: expect.objectContaining({ buy: 25 }) }),
    );
  });
});

describe('PlanRowPanel - Price and supplier zone (D4)', () => {
  const price: PriceAdvice = {
    advice: 'stale',
    last: { po_number: 'PO-500', issue_date: '2026-06-01', unit_cost: 10, currency: 'MYR', qty: 20 },
    previous: null,
    age_days: 87,
    movement_pct: null,
    currency_changed: false,
    standing_cost: null,
    standing_currency: null,
    standing_gap_pct: null,
    free_of_charge_lines: 0,
  } as unknown as PriceAdvice;

  it('shows the last price with its PO reference and date', () => {
    renderPanel({ price, line: line({ unit_cost: 10 }) });
    expect(screen.getByText(/PO-500/)).toBeInTheDocument();
    expect(screen.getByText(/2026-06-01/)).toBeInTheDocument();
  });

  it('offers the ranked shortlist as a searchable supplier select', () => {
    renderPanel({
      line: line({
        alternatives: [
          { supplier_code: 'S2', supplier_name: 'Beta', unit_cost: 8, currency: 'MYR', lead_time_days: 10, composite_score: 0, is_primary: false },
        ],
      }),
    });
    expect(screen.getByRole('option', { name: /Beta/ })).toBeInTheDocument();
  });

  it('shows the amber "Cheaper on file" line only when one is passed in', () => {
    const cheaper: CheaperAlternative = {
      supplier_code: 'S2', supplier_name: 'Beta', unit_cost: 8, currency: 'MYR', saving_pct: 20,
    };
    renderPanel({ cheaper });
    expect(screen.getByText(/Cheaper on file/)).toBeInTheDocument();
  });

  it('says nothing about a cheaper supplier when none was found', () => {
    renderPanel({ cheaper: null });
    expect(screen.queryByText(/Cheaper on file/)).not.toBeInTheDocument();
  });

  it('offers Use last price / Get new price radios, and writes the pick to the draft', () => {
    const { onEdit } = renderPanel();
    expect(screen.getByText('Use last price')).toBeInTheDocument();
    expect(screen.getByText('Get new price')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Get new price'));
    expect(onEdit).toHaveBeenCalledWith({ priceMode: 'ask_new' });
  });

  it('never purchased: reads "No price on file"', () => {
    renderPanel({ price: undefined, line: line({ unit_cost: 0, supplier: null }) });
    expect(screen.getByText('No price on file')).toBeInTheDocument();
  });

  // UAC D4's own last sentence: "Never purchased: 'No price on file', radio defaults to
  // Get new price."
  it('defaults the radio to Get new price when nothing has ever been purchased (UAC D4)', () => {
    renderPanel({ price: undefined, line: line({ unit_cost: 0, supplier: null }) });
    expect(screen.getByRole('radio', { name: 'Get new price' })).toBeChecked();
  });

  it('still defaults to Use last price when there IS one on file', () => {
    renderPanel({ price, line: line({ unit_cost: 10 }) });
    expect(screen.getByRole('radio', { name: 'Use last price' })).toBeChecked();
  });

  it('a saved answer outranks the default, even with no price on file', () => {
    renderPanel({
      price: undefined,
      line: line({ unit_cost: 0, supplier: null }),
      decision: { buy: 10, priceMode: 'use_last' },
    });
    expect(screen.getByRole('radio', { name: 'Use last price' })).toBeChecked();
  });

  it('clearing the supplier goes back to the row\'s proposed one and sends no code', () => {
    const { onEdit } = renderPanel({
      line: line({
        alternatives: [
          { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10, currency: 'MYR', lead_time_days: 30, composite_score: 0, is_primary: true },
          { supplier_code: 'S2', supplier_name: 'Beta', unit_cost: 8, currency: 'MYR', lead_time_days: 10, composite_score: 0, is_primary: false },
        ],
      }),
      edit: { supplierCode: 'S2' },
    });
    const select = screen.getByRole('combobox');
    expect(select).toHaveValue('S2');

    // What `SearchableSelect`'s own clear control does.
    fireEvent.change(select, { target: { value: '' } });
    expect(onEdit).toHaveBeenCalledWith({ supplierCode: '' });
  });

  it('a cleared supplier reads as the proposed one, not as an empty select', () => {
    renderPanel({
      line: line({
        alternatives: [
          { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10, currency: 'MYR', lead_time_days: 30, composite_score: 0, is_primary: true },
        ],
      }),
      edit: { supplierCode: '' },
    });
    expect(screen.getByRole('combobox')).toHaveValue('S1');
  });
});

describe('PlanRowPanel - AutoCount level + qty zone (D5)', () => {
  const level: LevelSuggestion = {
    product_id: 'p1', warehouse_id: 'w1', product_code: 'SKU-1', product_name: 'Product one',
    warehouse_code: 'BRW', warehouse_name: 'Butterworth', current_level: 20, current_source: null,
    suggested_level: 35, suggested_at: '2026-08-20', amended_level: null, amended_at: null,
    suggested_quantity: null, master_reorder_quantity: 10, reorder_qty: 40,
    basis: {
      adu: 1.2, lead_time_days: 30, safety_days: 14, safety_stock: 16.8, window_days: 90,
      months: [{ month: 'Jun', qty: 30 }, { month: 'Jul', qty: 40 }],
    } as unknown as LevelSuggestion['basis'],
  };

  it('shows a suggestion badge and the Level / Reorder qty inputs', () => {
    renderPanel({ levelSuggestion: level });
    expect(screen.getByLabelText('AutoCount level')).toBeInTheDocument();
    expect(screen.getByLabelText('AutoCount reorder qty')).toBeInTheDocument();
  });

  it('the reorder qty input reads the buyer\'s saved reorder_qty (R5), then the master figure', () => {
    renderPanel({ levelSuggestion: level });
    expect(screen.getByLabelText('AutoCount reorder qty')).toHaveValue(40);
  });

  it('editing the Level field writes to the draft', () => {
    const { onEdit } = renderPanel({ levelSuggestion: level });
    fireEvent.change(screen.getByLabelText('AutoCount level'), { target: { value: '50' } });
    expect(onEdit).toHaveBeenCalledWith({ level: 50 });
  });

  it('editing Reorder qty writes to the draft (R5)', () => {
    const { onEdit } = renderPanel({ levelSuggestion: level });
    fireEvent.change(screen.getByLabelText('AutoCount reorder qty'), { target: { value: '60' } });
    expect(onEdit).toHaveBeenCalledWith({ reorderQty: 60 });
  });

  it('a chart link opens the existing months chart in a dialog', () => {
    renderPanel({ levelSuggestion: level });
    fireEvent.click(screen.getByText('2-month chart'));
    expect(screen.getByText(/What left SKU-1 each month/)).toBeInTheDocument();
  });

  it('with no suggestion at all, says so and shows no chart link', () => {
    renderPanel();
    expect(screen.getByText('No level suggestion for this item.')).toBeInTheDocument();
    expect(screen.queryByText(/-month chart/)).not.toBeInTheDocument();
  });

  it('with no suggestion the Level input is dead, and Reorder qty is not', () => {
    // A level is AMENDED: the save refuses one with no suggestion to amend (422), so a
    // live input here could only ever fail - and it took the whole batch down with it.
    renderPanel();
    expect(screen.getByLabelText('AutoCount level')).toBeDisabled();
    expect(screen.getByLabelText('AutoCount reorder qty')).not.toBeDisabled();
  });

  it('with a suggestion the Level input is editable again', () => {
    renderPanel({ levelSuggestion: level });
    expect(screen.getByLabelText('AutoCount level')).not.toBeDisabled();
  });
});

describe('PlanRowPanel - Product health zone (D6)', () => {
  const economics: ProductEconomics = {
    product_id: 'p1', avg_sell_price: 20, sell_source: 'orders', sold_qty: 30, on_hand: 5,
    avg_monthly_out: 10, turnover_months: 0.5, no_movement: false, lifecycle_decision: null,
    lifecycle_decided_at: null, sold_recent_qty: 12, bought_recent_qty: 20,
    movement_class: 'fast_moving',
  };

  it('shows the verdict badge and the Keep selling / Discontinue radios', () => {
    renderPanel({ economics });
    expect(screen.getByText('Keep selling')).toBeInTheDocument();
    expect(screen.getByText('Discontinue')).toBeInTheDocument();
  });

  it('picking a radio writes lifecycle to the draft', () => {
    const { onEdit } = renderPanel({ economics });
    fireEvent.click(screen.getByText('Discontinue'));
    expect(onEdit).toHaveBeenCalledWith({ lifecycle: 'discontinue' });
  });

  it('with no economics on file, says so rather than showing an empty verdict', () => {
    renderPanel();
    expect(screen.getByText('No movement on file for this product.')).toBeInTheDocument();
  });
});

describe('PlanRowPanel - legacy run locks every input (D8)', () => {
  it('shows the lock reason once, and disables every writable control', () => {
    const level: LevelSuggestion = {
      product_id: 'p1', warehouse_id: 'w1', product_code: 'SKU-1', product_name: 'Product one',
      warehouse_code: 'BRW', warehouse_name: 'Butterworth', current_level: 20, current_source: null,
      suggested_level: 35, suggested_at: '2026-08-20', amended_level: null, amended_at: null,
      suggested_quantity: null, master_reorder_quantity: 10, reorder_qty: 40,
      basis: { adu: 1.2, lead_time_days: 30, safety_days: 14, safety_stock: 16.8, window_days: 90, months: [] } as unknown as LevelSuggestion['basis'],
    };
    const economics: ProductEconomics = {
      product_id: 'p1', avg_sell_price: 20, sell_source: 'orders', sold_qty: 30, on_hand: 5,
      avg_monthly_out: 10, turnover_months: 0.5, no_movement: false, lifecycle_decision: null,
      lifecycle_decided_at: null, sold_recent_qty: 12, bought_recent_qty: 20,
      movement_class: 'fast_moving',
    };
    renderPanel({
      disabled: true,
      lockReason: 'This run predates decisions - every input is read-only.',
      levelSuggestion: level,
      economics,
    });

    expect(screen.getByText('This run predates decisions - every input is read-only.')).toBeInTheDocument();
    expect(screen.getByLabelText('Units to buy')).toBeDisabled();
    expect(screen.getByLabelText('MOQ')).toBeDisabled();
    expect(screen.getByLabelText('AutoCount level')).toBeDisabled();
    expect(screen.getByLabelText('AutoCount reorder qty')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Use suggestion' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Skip' })).toBeDisabled();
  });
});

describe('PlanRowPanel - no stock-as-of line, no location table (D9)', () => {
  it('never mentions "Live stock as of" inside the panel', () => {
    renderPanel();
    expect(screen.queryByText(/Live stock as of/)).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('explains no rules on screen - the staleness rule is not a sentence here', () => {
    renderPanel({ price: undefined });
    expect(screen.queryByText(/treated as stale/)).not.toBeInTheDocument();
  });
});

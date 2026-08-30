/**
 * PlanRowDialogs - six numbers, six lightboxes (plan 4.6, UAC F1-F6).
 *
 * `PlanNumberButton` is the trigger every number renders as (F1: no hover popovers, no (i)
 * icons); `PlanRowDialog` is the one dialog the grid mounts, keyed by which number was
 * pressed. `poolLocationLabel` is tested directly first - it decides the "to BRW" wording
 * every SPO/PO tab and title carries, and its own edge case (a grouped row with no member
 * AT the pool) is the one the plan's Phase 2 deviations section calls out by name.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import { groupPlanLinesByChannel } from '../lib/planLineGrouping';
import type { PoReceipt } from '../lib/poCover';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

// The row-expand documents panel is its own suite; here it only has to exist so the
// On-hand table's row-click branch never throws.
vi.mock('../../../project-sales/fulfilment-planning/components/StockDocumentsPanel', () => ({
  StockDocumentsPanel: () => <div data-testid="stock-documents-panel" />,
}));

const useLocationStock = vi.fn();
const useRecommendationDemand = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useLocationStock: (...a: unknown[]) => useLocationStock(...a),
  useRecommendationDemand: (...a: unknown[]) => useRecommendationDemand(...a),
}));

const getSpoHistory = vi.fn();
const getPoHistoryToPool = vi.fn();
vi.mock('../services/planEditsService', () => ({
  getSpoHistory: (...a: unknown[]) => getSpoHistory(...a),
  getPoHistoryToPool: (...a: unknown[]) => getPoHistoryToPool(...a),
}));

import { PlanNumberButton } from './PlanNumberButton';
import { PlanRowDialog, poolLocationLabel, type PlanDialogKind } from './PlanRowDialogs';

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 23, recommended_qty: 23, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -23, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: null, master_moq: null, moq_is_override: false,
    order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 230, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 24,
    project_committed: 0, retail_committed: 24,
    segment: 'dealer', pool_warehouse_id: null, pool_warehouse_code: null,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

// ---------------------------------------------------------------------------
// poolLocationLabel (R15 / plan 5.11 / Phase 2 deviation "the pool is resolved from...")
// ---------------------------------------------------------------------------

describe('poolLocationLabel', () => {
  it('prefers the backend-named pool_warehouse_code, ungrouped or not', () => {
    const l = line({ pool_warehouse_code: 'BRW' });
    expect(poolLocationLabel(l)).toBe('BRW');
  });

  it('falls back to the row\'s own warehouse code when ungrouped and no pool code was named', () => {
    const l = line({ warehouse_code: 'DC1', pool_warehouse_code: null });
    expect(poolLocationLabel(l)).toBe('DC1');
  });

  it('on a grouped row, names the member that IS the pool (by pool id match)', () => {
    const grouped = groupPlanLinesByChannel([
      line({ id: 'r1', warehouse_id: 'w1', warehouse_code: 'BRW', pool_warehouse_id: 'w1' }),
      line({ id: 'r2', warehouse_id: 'w2', warehouse_code: 'BRW-BB', pool_warehouse_id: 'w1' }),
    ]);
    const groupRow = grouped.find((l) => l.id.startsWith('group:')) as PlanLine;
    expect(poolLocationLabel(groupRow)).toBe('BRW');
  });

  it('returns null when no member sits at the pool - never names a project bin instead', () => {
    // Neither member's warehouse_id matches the pool id (w9, nobody's own location), and
    // neither carries its own pool_warehouse_code - the live-data shape the plan calls out
    // by name (32MM TAIL PIECE COUPLING): the two members are project bins, the pool
    // itself has no recommendation row at all.
    const grouped = groupPlanLinesByChannel([
      line({ id: 'r1', warehouse_id: 'w2', warehouse_code: 'BRW-BB', pool_warehouse_id: 'w9' }),
      line({ id: 'r2', warehouse_id: 'w3', warehouse_code: 'BRW-AM', pool_warehouse_id: 'w9' }),
    ]);
    const groupRow = grouped.find((l) => l.id.startsWith('group:')) as PlanLine;
    expect(poolLocationLabel(groupRow)).toBeNull();
  });

  it('a grouped row with no pool id at all also returns null, not a guess', () => {
    const grouped = groupPlanLinesByChannel([
      line({ id: 'r1', warehouse_id: 'w2', warehouse_code: 'BRW-BB', pool_warehouse_id: null }),
      line({ id: 'r2', warehouse_id: 'w3', warehouse_code: 'BRW-AM', pool_warehouse_id: null }),
    ]);
    const groupRow = grouped.find((l) => l.id.startsWith('group:')) as PlanLine;
    expect(poolLocationLabel(groupRow)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// PlanNumberButton - the trigger every one of the six numbers renders as (F1)
// ---------------------------------------------------------------------------

describe('PlanNumberButton (F1)', () => {
  it('a live number is a button that opens its dialog on click', () => {
    const onClick = vi.fn();
    render(<PlanNumberButton value="184" label="Suggested qty" onClick={onClick} />);
    screen.getByRole('button', { name: 'Suggested qty' }).click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('a disabled number (nothing to open) renders as plain text, not a button', () => {
    const onClick = vi.fn();
    render(<PlanNumberButton value="0" label="Suggested qty" onClick={onClick} disabled />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('never bubbles the click up to the row (which would toggle the expand panel too)', () => {
    const onClick = vi.fn();
    const rowClick = vi.fn();
    render(
      <div onClick={rowClick}>
        <PlanNumberButton value="184" label="Suggested qty" onClick={onClick} />
      </div>,
    );
    screen.getByRole('button', { name: 'Suggested qty' }).click();
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(rowClick).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// PlanRowDialog - one dialog, six bodies
// ---------------------------------------------------------------------------

function renderDialog(
  kind: PlanDialogKind,
  l: PlanLine,
  extra: { poReceipts?: PoReceipt[]; ledger?: React.ReactNode } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlanRowDialog
        request={{ kind, line: l }}
        onOpenChange={() => {}}
        runId="run-1"
        poReceipts={extra.poReceipts}
        ledger={extra.ledger}
      />
    </QueryClientProvider>,
  );
}

describe('PlanRowDialog - suggested', () => {
  it('renders no dialog at all when nothing was requested', () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <PlanRowDialog request={null} onOpenChange={() => {}} runId="run-1" />
      </QueryClientProvider>,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows the passed-in ledger body', () => {
    renderDialog('suggested', line(), { ledger: <div>the-ledger-body</div> });
    expect(screen.getByText('the-ledger-body')).toBeInTheDocument();
    expect(screen.getByText(/Suggested qty - SKU-1/)).toBeInTheDocument();
  });

  it('falls back to a plain message when no ledger was supplied', () => {
    renderDialog('suggested', line());
    expect(screen.getByText('Nothing to explain here.')).toBeInTheDocument();
  });
});

describe('PlanRowDialog - project / retail demand (F2, F3)', () => {
  const openData = {
    lines: [{
      so_number: 'OI-1', customer_label: 'ACME Sdn Bhd', project_title: 'Tower A',
      agent_label: 'Agent 1', unit_price: 12.5, qty: 10, required_date: '2026-09-01',
    }],
    total: 1, shown: 1, committed_total: 10, unlocated_total: 0, locations: ['BRW'], scope: 'warehouse',
  };
  const historyData = {
    history_lines: [{
      so_number: 'SO-9', customer_label: 'Beta Sdn Bhd', project_title: null,
      agent_label: null, unit_price: 9.5, qty: 5, order_date: '2026-01-01', delivered: true,
    }],
    history_total: 1,
  };

  it('project: "Order inquiries (N open)" and "SO history", with project_title as a column (F2)', () => {
    useRecommendationDemand.mockImplementation((_r, _id, _en, _ch, scope) =>
      scope === 'product' ? { data: historyData, isLoading: false } : { data: openData, isLoading: false },
    );
    renderDialog('project', line());

    expect(screen.getByText('Order inquiries (1 open)')).toBeInTheDocument();
    expect(screen.getByText('SO history (1)')).toBeInTheDocument();
    expect(screen.getByText('Tower A')).toBeInTheDocument();
    expect(screen.getByText('ACME Sdn Bhd')).toBeInTheDocument();
    expect(useRecommendationDemand).toHaveBeenCalledWith('run-1', 'r1', true, 'project');
    expect(useRecommendationDemand).toHaveBeenCalledWith('run-1', 'r1', true, 'project', 'product');
  });

  it('retail: "Open sales orders (N)" and "SO history" (F3)', () => {
    useRecommendationDemand.mockImplementation((_r, _id, _en, _ch, scope) =>
      scope === 'product' ? { data: historyData, isLoading: false } : { data: openData, isLoading: false },
    );
    renderDialog('retail', line());

    expect(screen.getByText('Open sales orders (1)')).toBeInTheDocument();
    expect(useRecommendationDemand).toHaveBeenCalledWith('run-1', 'r1', true, 'retail');
  });

  it('an empty channel says so rather than an empty table', () => {
    useRecommendationDemand.mockReturnValue({ data: { lines: [], history_lines: [] }, isLoading: false });
    renderDialog('project', line());
    expect(screen.getByText('Nothing open on this channel for this product.')).toBeInTheDocument();
  });
});

describe('PlanRowDialog - On hand (F4)', () => {
  const locations = [
    {
      warehouse_id: 'w1', warehouse_code: 'BRW', on_hand: 100, reserved: 10, free: 90,
      so_qty: 5, spo_qty: 20, available: 105, is_pool: true, po_qty: 30,
    },
    {
      warehouse_id: 'w2', warehouse_code: 'BRW-BB', on_hand: 12, reserved: 2, free: 10,
      so_qty: 12, spo_qty: 0, available: -2, is_pool: false, po_qty: null,
    },
  ];

  it('shows only the site-pool row(s), never a project bin, when a pool row exists', () => {
    useLocationStock.mockReturnValue({
      data: { product_id: 'p1', as_of: '2026-08-20T10:00:00', locations },
      isLoading: false,
    });
    renderDialog('on_hand', line());

    expect(screen.getByText('BRW')).toBeInTheDocument();
    expect(screen.queryByText('BRW-BB')).not.toBeInTheDocument();
  });

  it('lists EVERY site pool, zeros included (R16)', () => {
    // "DC1 has none" is a fact a buyer choosing where to buy into needs to read; a
    // missing row says only that nobody told them, and the two look the same on screen.
    useLocationStock.mockReturnValue({
      data: {
        product_id: 'p1', as_of: null,
        locations: [
          ...locations,
          { warehouse_id: 'w3', warehouse_code: 'DC1', on_hand: 0, reserved: 0, free: 0,
            so_qty: 0, spo_qty: 0, available: 0, is_pool: true, po_qty: 0 },
          { warehouse_id: 'w4', warehouse_code: 'MWH', on_hand: 0, reserved: 0, free: 0,
            so_qty: 0, spo_qty: 0, available: 0, is_pool: true, po_qty: 0 },
        ],
      },
      isLoading: false,
    });
    renderDialog('on_hand', line());

    expect(screen.getByText('BRW')).toBeInTheDocument();
    expect(screen.getByText('DC1')).toBeInTheDocument();
    expect(screen.getByText('MWH')).toBeInTheDocument();
    expect(screen.queryByText('BRW-BB')).not.toBeInTheDocument();
  });

  it('shows no project bin at all, even when every pool row is missing', () => {
    // No fall-back to the whole list any more: a project bin's stock is claimed by an
    // Order Inquiry, and the pool-only rule does not lapse because a payload is thin.
    useLocationStock.mockReturnValue({
      data: {
        product_id: 'p1', as_of: null,
        locations: locations.map((l) => ({ ...l, is_pool: false })),
      },
      isLoading: false,
    });
    renderDialog('on_hand', line());

    expect(screen.queryByText('BRW-BB')).not.toBeInTheDocument();
    expect(screen.getByText('No site pool holds this product.')).toBeInTheDocument();
  });

  it('the dialog title names the pool it counts (R16)', () => {
    useLocationStock.mockReturnValue({
      data: { product_id: 'p1', as_of: null, locations },
      isLoading: false,
    });
    renderDialog('on_hand', line());

    expect(screen.getByRole('heading', { name: /On hand BRW/ })).toBeInTheDocument();
  });

  it('states "Stock as of" using the response\'s own as_of (R7), not the request time', () => {
    useLocationStock.mockReturnValue({
      data: { product_id: 'p1', as_of: '2026-08-20T10:00:00', locations },
      isLoading: false,
    });
    renderDialog('on_hand', line());
    expect(screen.getByText(/Stock as of/)).toBeInTheDocument();
  });

  it('says nothing about "as of" when the backend gives no date at all', () => {
    useLocationStock.mockReturnValue({
      data: { product_id: 'p1', as_of: null, locations: [] },
      isLoading: false,
    });
    renderDialog('on_hand', line());
    expect(screen.queryByText(/Stock as of/)).not.toBeInTheDocument();
  });

  it('a product with no stock rows at all says so', () => {
    useLocationStock.mockReturnValue({ data: { product_id: 'p1', as_of: null, locations: [] }, isLoading: false });
    renderDialog('on_hand', line());
    expect(screen.getByText('No site pool holds this product.')).toBeInTheDocument();
  });
});

describe('PlanRowDialog - SPO (F5)', () => {
  it('tabs read "Open to BRW" / "History to BRW" when the pool is named', async () => {
    getSpoHistory.mockResolvedValue({
      open: [{ spo_number: 'SPO-1', supplier_name: 'Acme', qty: 10, received_qty: 0, eta: '2026-09-01', arrived_at: null, status: 'open' }],
      history: [],
    });
    renderDialog('spo', line({ pool_warehouse_code: 'BRW' }));

    expect(await screen.findByText('Open to BRW (1)')).toBeInTheDocument();
    expect(screen.getByText('History to BRW (0)')).toBeInTheDocument();
    expect(getSpoHistory).toHaveBeenCalledWith('run-1', 'p1');
  });

  it('drops the location wording entirely when the pool cannot be named', async () => {
    getSpoHistory.mockResolvedValue({ open: [], history: [] });
    renderDialog('spo', line({ pool_warehouse_code: null, warehouse_code: null }));

    expect(await screen.findByText('Open (0)')).toBeInTheDocument();
    expect(screen.queryByText(/to BRW/)).not.toBeInTheDocument();
  });
});

describe('PlanRowDialog - PO (F6)', () => {
  const poReceipts: PoReceipt[] = [
    { po_number: 'PO-100', status: 'active', expected_date: '2026-09-10', remaining: 50 },
  ];

  it('the Open tab reads from poReceipts and never shows Supplier or Unit price columns', () => {
    getPoHistoryToPool.mockResolvedValue({ history: [] });
    renderDialog('po', line({ pool_warehouse_code: 'BRW' }), { poReceipts });

    expect(screen.getByText('Open to BRW (1)')).toBeInTheDocument();
    const openTable = screen.getByText('PO-100').closest('table') as HTMLElement;
    expect(within(openTable).getByText('Still to come')).toBeInTheDocument();
    expect(within(openTable).queryByText('Supplier')).not.toBeInTheDocument();
    expect(within(openTable).queryByText('Unit price')).not.toBeInTheDocument();
  });

  it('the History tab carries Supplier and Unit price (BRW pool key, R15/F6)', async () => {
    getPoHistoryToPool.mockResolvedValue({
      history: [{
        po_number: 'PO-90', supplier_name: 'Acme', qty: 30, unit_cost: 9.5, currency: 'MYR',
        issued_at: '2026-07-01', eta: '2026-07-20', status: 'received',
      }],
    });
    renderDialog('po', line({ pool_warehouse_code: 'BRW' }), { poReceipts: [] });

    // Radix Tabs does not render an inactive tab's content at all by default - the
    // History body only exists once its trigger is selected.
    fireEvent.mouseDown(await screen.findByText('History to BRW (1)'));

    expect(await screen.findByText('PO-90')).toBeInTheDocument();
    expect(getPoHistoryToPool).toHaveBeenCalledWith('run-1', 'p1', 'BRW');
    const historyTable = screen.getByText('PO-90').closest('table') as HTMLElement;
    expect(within(historyTable).getByText('Supplier')).toBeInTheDocument();
    expect(within(historyTable).getByText('Unit price')).toBeInTheDocument();
    expect(within(historyTable).getByText('Acme')).toBeInTheDocument();
  });

  it('names no destination-less or wrong-pool line - an empty history says so, naming the pool', async () => {
    getPoHistoryToPool.mockResolvedValue({ history: [] });
    renderDialog('po', line({ pool_warehouse_code: 'BRW' }), { poReceipts: [] });

    fireEvent.mouseDown(await screen.findByText('History to BRW (0)'));

    expect(
      await screen.findByText('No purchase order raised here names BRW as its destination.'),
    ).toBeInTheDocument();
  });

  it('the dialog title names the pool for a PO/SPO request, "to BRW"', () => {
    getPoHistoryToPool.mockResolvedValue({ history: [] });
    renderDialog('po', line({ pool_warehouse_code: 'BRW' }), { poReceipts: [] });
    expect(screen.getByText('PO - SKU-1 - to BRW')).toBeInTheDocument();
  });
});

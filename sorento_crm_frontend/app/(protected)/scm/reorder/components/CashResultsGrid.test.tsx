/**
 * SCM M4 Slice B — CashResultsGrid decision layer (AC-M4.5/M4.7/M4.8/M4.9/M4.14).
 *   - leftmost selection column (select-all checkbox) when the decision layer is on
 *   - Decision badge states: Pending / Accepted → PO ref / Adjusted / Rejected
 *   - per-row action menu (Accept / Adjust… / Reject…) wired to the callbacks
 *   - unified "Actions" dropdown appears on selection and is HIDDEN when the
 *     selection has no still-pending rows
 *
 * The dropdown-menu module is stubbed to render inline (established repo pattern,
 * see SlaExtendAction.test) so menu items are assertable without a Radix portal.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

// Render dropdown menu items inline so Accept/Adjust/Reject are assertable.
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <>{children}</>,
  DropdownMenuContent: ({ children }: any) => <div data-testid="menu-content">{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: any) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuSeparator: () => <hr />,
}));

import { CashResultsGrid } from './CashResultsGrid';
import type { ReorderRecommendation } from '../types/reorder.types';
import type { RecDecision } from '../types/decisions.types';

function rec(over: Partial<ReorderRecommendation>): ReorderRecommendation {
  return {
    id: 'rec-1',
    type: 'buy',
    sku: 'CW-BASIN-450',
    product_name: 'Ceramic Wash Basin 450mm',
    abc_class: 'A',
    xyz_class: 'X',
    warehouse_code: 'WH-KL',
    warehouse_name: 'Kuala Lumpur DC',
    is_network: false,
    allocation: null,
    order_qty: 320,
    reorder_point: 280,
    min_qty: null,
    max_qty: null,
    order_up_to: null,
    net_position: 240,
    days_of_cover: 9,
    reason: 'reorder_point',
    reason_label: 'net ≤ ROP',
    confidence: 'high',
    sample_size: 40,
    supplier: {
      supplier_code: 'SUP-ACME',
      supplier_name: 'Acme Sanitary',
      unit_cost: 42,
      lead_time_days: 14,
      composite_score: 88,
      is_primary: true,
    },
    alternatives: [],
    is_exception: false,
    disposition_action: null,
    transfer_flag: null,
    recommended_qty: 80,
    forecast_daily_demand: 11,
    lead_time_days: 14,
    lead_time_source: 'measured',
    safety_stock: 77,
    safety_stock_method: 'fixed_days',
    safety_stock_fallback: null,
    service_level: 0.95,
    safety_days: 7,
    review_days: 30,
    moq: 10,
    order_multiple: 5,
    policy_type: 'reorder_point',
    supplier_selection: 'primary',
    unit_cost: 42,
    cash_impact: 13440,
    rank: 1,
    rank_score: 0.82,
    funding_status: 'funded',
    days_to_stockout: 12,
    rank_factors: [],
    ...over,
  } as ReorderRecommendation;
}

const decisionCallbacks = () => ({
  onAccept: vi.fn(),
  onAdjust: vi.fn(),
  onReject: vi.fn(),
  onBulkAccept: vi.fn(),
  onBulkReject: vi.fn(),
});

beforeEach(() => cleanup());

describe('CashResultsGrid — decision layer structure (AC-M4.14)', () => {
  it('renders the leftmost selection column when the decision layer is enabled', () => {
    const cb = decisionCallbacks();
    render(
      <CashResultsGrid rows={[rec({})]} variant="funded" isLoading={false} onRowClick={() => {}} selectable {...cb} />,
    );
    expect(screen.getByLabelText('Select all rows on this page')).toBeInTheDocument();
    expect(screen.getAllByLabelText('Select row').length).toBe(1);
  });

  it('renders every Decision badge state incl. the accepted → PO ref link', () => {
    const cb = decisionCallbacks();
    const rows = [
      rec({ id: 'r-pending', sku: 'SKU-PEND' }),
      rec({ id: 'r-acc', sku: 'SKU-ACC' }),
      rec({ id: 'r-adj', sku: 'SKU-ADJ' }),
      rec({ id: 'r-dis', sku: 'SKU-DIS' }),
    ];
    const decisionsById: Record<string, RecDecision> = {
      'r-acc': {
        recommendation_id: 'r-acc',
        status: 'accepted',
        override_qty: null,
        override_supplier_code: null,
        override_supplier_name: null,
        reason_text: null,
        draft_po_number: 'PO-DRAFT-0007',
        draft_po_id: 'po-7',
      },
      'r-adj': {
        recommendation_id: 'r-adj',
        status: 'adjusted',
        override_qty: 500,
        override_supplier_code: null,
        override_supplier_name: null,
        reason_text: 'MOQ',
        draft_po_number: 'PO-DRAFT-0008',
        draft_po_id: 'po-8',
      },
      'r-dis': {
        recommendation_id: 'r-dis',
        status: 'dismissed',
        override_qty: null,
        override_supplier_code: null,
        override_supplier_name: null,
        reason_text: 'overstocked',
        draft_po_number: null,
        draft_po_id: null,
      },
    };
    render(
      <CashResultsGrid
        rows={rows}
        variant="funded"
        isLoading={false}
        onRowClick={() => {}}
        decisionsById={decisionsById}
        selectable
        {...cb}
      />,
    );
    expect(screen.getByText('Pending')).toBeInTheDocument(); // r-pending, no decision
    // "Accepted" also appears as the disabled row-menu item — the badge is one of them.
    expect(screen.getAllByText('Accepted').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Adjusted')).toBeInTheDocument();
    expect(screen.getByText('Rejected')).toBeInTheDocument();
    // Accepted row deep-links to its draft PO by human number (never a UUID).
    const poLink = screen.getByRole('link', { name: /PO-DRAFT-0007/ });
    expect(poLink).toHaveAttribute('href', '/scm/purchase-orders/po-7');
  });
});

describe('CashResultsGrid — per-row action menu (AC-M4.5/M4.7/M4.8)', () => {
  it('offers Accept / Adjust… / Reject… wired to the callbacks', () => {
    const cb = decisionCallbacks();
    const row = rec({ id: 'rec-x' });
    render(
      <CashResultsGrid rows={[row]} variant="funded" isLoading={false} onRowClick={() => {}} selectable {...cb} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /^Accept$/ }));
    fireEvent.click(screen.getByRole('button', { name: /Adjust/ }));
    fireEvent.click(screen.getByRole('button', { name: /Reject/ }));
    expect(cb.onAccept).toHaveBeenCalledWith(row);
    expect(cb.onAdjust).toHaveBeenCalledWith(row);
    expect(cb.onReject).toHaveBeenCalledWith(row);
  });

  it('disables Accept once the row is already accepted', () => {
    const cb = decisionCallbacks();
    const decisionsById: Record<string, RecDecision> = {
      'rec-x': {
        recommendation_id: 'rec-x',
        status: 'accepted',
        override_qty: null,
        override_supplier_code: null,
        override_supplier_name: null,
        reason_text: null,
        draft_po_number: 'PO-DRAFT-1',
        draft_po_id: 'po-1',
      },
    };
    render(
      <CashResultsGrid
        rows={[rec({ id: 'rec-x' })]}
        variant="funded"
        isLoading={false}
        onRowClick={() => {}}
        decisionsById={decisionsById}
        selectable
        {...cb}
      />,
    );
    expect(screen.getByRole('button', { name: /Accepted/ })).toBeDisabled();
  });
});

describe('CashResultsGrid — unified Actions dropdown gating (AC-M4.9)', () => {
  it('shows no Actions button until a row is selected, then reveals it', () => {
    const cb = decisionCallbacks();
    render(
      <CashResultsGrid
        rows={[rec({ id: 'a' }), rec({ id: 'b', sku: 'SKU-B' })]}
        variant="funded"
        isLoading={false}
        onRowClick={() => {}}
        selectable
        {...cb}
      />,
    );
    expect(screen.queryByRole('button', { name: /^Actions$/ })).toBeNull();
    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    expect(screen.getByRole('button', { name: /^Actions$/ })).toBeInTheDocument();
  });

  it('keeps the Actions button HIDDEN when every selected row is already decided', () => {
    const cb = decisionCallbacks();
    const decisionsById: Record<string, RecDecision> = {
      a: {
        recommendation_id: 'a',
        status: 'accepted',
        override_qty: null,
        override_supplier_code: null,
        override_supplier_name: null,
        reason_text: null,
        draft_po_number: 'PO-DRAFT-1',
        draft_po_id: 'po-1',
      },
    };
    render(
      <CashResultsGrid
        rows={[rec({ id: 'a' })]}
        variant="funded"
        isLoading={false}
        onRowClick={() => {}}
        decisionsById={decisionsById}
        selectable
        {...cb}
      />,
    );
    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    expect(screen.queryByRole('button', { name: /^Actions$/ })).toBeNull();
  });
});

describe('CashResultsGrid — needs_cost read-only variant (AC-M4.16)', () => {
  it('renders the empty state with no selection column or row actions', () => {
    render(
      <CashResultsGrid rows={[]} variant="needs_cost" isLoading={false} onRowClick={() => {}} />,
    );
    expect(screen.getByText('Needs cost')).toBeInTheDocument();
    expect(screen.queryByLabelText('Select all rows on this page')).toBeNull();
  });
});

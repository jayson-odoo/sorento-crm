import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReorderRecommendation } from '../types/reorder.types';
import type { RecommendationPage } from '../services/reorderRunService';

// jsdom polyfills required by ScrollArea / DataGrid.
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

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// DataGrid persists column prefs via this hook (fires network) - stub it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const useReorderRecommendations = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useReorderRecommendations: (...a: unknown[]) => useReorderRecommendations(...a),
}));

import { ReorderResultsGrid } from './ReorderResultsGrid';

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
      supplier_name: 'Acme Sanitary Sdn Bhd',
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
    unit_cost: null,
    cash_impact: null,
    rank: null,
    rank_score: null,
    funding_status: null,
    days_to_stockout: null,
    rank_factors: [],
    ...over,
  };
}

function page(data: ReorderRecommendation[]): RecommendationPage {
  return {
    data,
    pagination: { page: 1, limit: 25, total: data.length, total_pages: 1 },
  };
}

function mockPage(data: ReorderRecommendation[]) {
  useReorderRecommendations.mockReturnValue({
    data: page(data),
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
}

beforeEach(() => useReorderRecommendations.mockReset());

describe('ReorderResultsGrid', () => {
  it('renders a plain buy row with its supplier + trigger', () => {
    mockPage([rec({})]);
    render(<ReorderResultsGrid runId="run-1" enabled typeFilter="" onTypeFilterChange={() => {}} />);
    expect(screen.getByText('CW-BASIN-450')).toBeInTheDocument();
    expect(screen.getByText('Acme Sanitary Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('net ≤ ROP')).toBeInTheDocument();
    expect(screen.getByText('Buy')).toBeInTheDocument();
  });

  it('renders a NETWORK allocation row (chevron popover trigger, no warehouse code)', () => {
    mockPage([
      rec({
        id: 'rec-net',
        sku: 'WC-CLOSE-COUPLE',
        warehouse_code: null,
        warehouse_name: null,
        is_network: true,
        allocation: [
          { warehouse_code: 'WH-KL', warehouse_name: 'Kuala Lumpur DC', qty: 90 },
          { warehouse_code: 'WH-JB', warehouse_name: 'Johor Bahru DC', qty: 60 },
        ],
        order_qty: 150,
      }),
    ]);
    render(<ReorderResultsGrid runId="run-1" enabled typeFilter="" onTypeFilterChange={() => {}} />);
    // the Network badge stands in for the warehouse cell on aggregated rows
    expect(screen.getByText('Network')).toBeInTheDocument();
    expect(screen.getByText('WC-CLOSE-COUPLE')).toBeInTheDocument();
  });

  it('renders a no-supplier EXCEPTION row (Exception chip + No supplier badge)', () => {
    mockPage([
      rec({
        id: 'rec-exc',
        type: 'exception',
        sku: 'AC-TOWEL-BAR',
        order_qty: null,
        supplier: null,
        alternatives: [],
        is_exception: true,
        reason_label: 'no linked supplier',
      }),
    ]);
    render(<ReorderResultsGrid runId="run-1" enabled typeFilter="" onTypeFilterChange={() => {}} />);
    expect(screen.getByText('Exception')).toBeInTheDocument();
    expect(screen.getByText('No supplier')).toBeInTheDocument();
  });

  it('renders a disposition row with its action + advisory transfer flag', () => {
    mockPage([
      rec({
        id: 'rec-disp',
        type: 'disposition',
        sku: 'MX-SHOWER-CHR',
        order_qty: null,
        reorder_point: null,
        net_position: 640,
        reason: 'overstock',
        reason_label: 'days-of-cover > 180',
        confidence: 'medium',
        supplier: null,
        alternatives: [],
        disposition_action: 'hold',
        transfer_flag: 'consider transfer 60: WH-JB → WH-KL',
      }),
    ]);
    render(<ReorderResultsGrid runId="run-1" enabled typeFilter="" onTypeFilterChange={() => {}} />);
    expect(screen.getByText('Disposition')).toBeInTheDocument();
    expect(screen.getByText('Hold')).toBeInTheDocument();
    expect(screen.getByText('consider transfer 60: WH-JB → WH-KL')).toBeInTheDocument();
  });

  it('renders the empty state when the run produced no recommendations', () => {
    mockPage([]);
    render(<ReorderResultsGrid runId="run-1" enabled typeFilter="" onTypeFilterChange={() => {}} />);
    expect(screen.getByText('No recommendations for this run.')).toBeInTheDocument();
  });

  it('renames "ROP" to "Reorder point" and spells out metrics via header tooltips', () => {
    mockPage([rec({})]);
    render(<ReorderResultsGrid runId="run-1" enabled typeFilter="" onTypeFilterChange={() => {}} />);
    // primary word is readable; (ROP) is a small secondary
    expect(screen.getByText('Reorder point')).toBeInTheDocument();
    expect(screen.getByText('(ROP)')).toBeInTheDocument();
    // header info tooltips are keyboard-accessible - the plain-language copy is the aria-label
    expect(screen.getByLabelText(/The stock level that triggers a reorder/i)).toBeInTheDocument();
    expect(
      screen.getByLabelText(/Net position = on hand \+ on order − committed/i),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/net position lasts at the forecast demand/i),
    ).toBeInTheDocument();
  });
});

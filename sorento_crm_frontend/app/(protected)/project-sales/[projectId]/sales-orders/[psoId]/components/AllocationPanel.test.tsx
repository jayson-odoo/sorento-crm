/**
 * P9 - the allocation worklist (AC-H1 to AC-H5), read-only since Stage 1C.
 *
 * The question this screen exists to answer is "which of these lines still has nowhere to
 * come from", so an unsourced line is never filtered away and a line waiting on another
 * project reads as waiting rather than as sourced. The facts pinned hardest here are that
 * a pending claim carries NO stock location (nothing moves on silence) and that this
 * panel decides nothing: supply is composed and confirmed for the whole sales order in
 * Fulfilment Planning, so the panel offers the way there and no write of its own.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  AllocationCandidateList,
  AllocationLineRow,
  AllocationSourceRow,
} from '../../../../_shared/types/projectAllocation.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1',
  useSearchParams: () => new URLSearchParams(''),
}));

// Without this the shared DataGrid sits in its column-preferences fetch forever and renders
// skeleton rows instead of data.
const listingKeys: (string | null | undefined)[] = [];
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: vi.fn(), isLoading: false };
  },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

const listSalesOrderAllocations = vi.fn();
const listAllocationCandidates = vi.fn();

vi.mock('../../../../_shared/services/projectAllocationService', () => ({
  listSalesOrderAllocations: (...args: unknown[]) => listSalesOrderAllocations(...args),
  listAllocationCandidates: (...args: unknown[]) => listAllocationCandidates(...args),
  listAllocationClaims: vi.fn(),
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

import { AllocationPanel } from './AllocationPanel';

function source(overrides: Partial<AllocationSourceRow> = {}): AllocationSourceRow {
  return {
    id: 'src-1',
    source_type: 'brw',
    warehouse_id: 'wh-brw',
    warehouse_code: 'BRW',
    warehouse_name: 'Master location',
    qty: '10',
    confirmed: true,
    ...overrides,
  };
}

function line(overrides: Partial<AllocationLineRow> = {}): AllocationLineRow {
  return {
    line_id: 'l1',
    line_no: 1,
    product_id: 'prod-1',
    product_code: 'SRT382-6',
    description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
    qty: '10',
    uom: 'UNIT',
    delivery_date: '2026-07-01',
    state: 'unallocated',
    stock_location: null,
    allocated_qty: '0',
    outstanding_qty: '10',
    sources: [],
    ...overrides,
  };
}

const SOURCED = line({
  line_id: 'l2',
  line_no: 2,
  product_code: 'CB6633',
  description: 'CABANA S/STEEL FLOOR GRATING 6"',
  state: 'confirmed',
  stock_location: 'BRW',
  allocated_qty: '10',
  outstanding_qty: '0',
  sources: [source()],
});

const WAITING = line({
  line_id: 'l3',
  line_no: 3,
  product_code: 'SRTFV1001',
  description: 'SENSOR URINAL FLUSH VALVE',
  qty: '5',
  state: 'pending_claim',
  stock_location: null,
  allocated_qty: '0',
  outstanding_qty: '5',
  sources: [
    source({
      id: 'src-3',
      source_type: 'other_project',
      warehouse_id: 'wh-kl',
      warehouse_code: 'WH-KL',
      source_project_id: 'p2',
      source_project_code: 'PRJ-000042',
      source_project_cs_name: 'Aisyah',
      qty: '5',
      confirmed: false,
      claim_id: 'c1',
      claim_state: 'requested',
    }),
  ],
});

const CANDIDATES: AllocationCandidateList = {
  line_id: 'l1',
  line_no: 1,
  product_code: 'SRT382-6',
  description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
  qty: '10',
  uom: 'UNIT',
  delivery_date: '2026-07-01',
  project_code: 'PRJ-000001',
  brw_warehouse_code: 'BRW',
  candidates: [],
  plan: [],
  shortfall: '0',
  covered: false,
};

function envelope(rows: AllocationLineRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 100 };
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AllocationPanel psoId="so-1" />
    </QueryClientProvider>,
  );
}

/** Radix opens its menus on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  listSalesOrderAllocations.mockResolvedValue(envelope([]));
  listAllocationCandidates.mockResolvedValue(CANDIDATES);
});

describe('AllocationPanel', () => {
  it('shows skeleton rows while the allocation loads, not an empty order', () => {
    listSalesOrderAllocations.mockReturnValue(new Promise(() => {}));

    const { container } = renderPanel();

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByText('This order has no lines')).not.toBeInTheDocument();
  });

  it('says the order has no lines and what to do about it, rather than a blank box', async () => {
    renderPanel();

    expect(await screen.findByText('This order has no lines')).toBeInTheDocument();
    expect(
      screen.getByText('Rebuild the order from its purchase order and delivery schedule.'),
    ).toBeInTheDocument();
  });

  it('states a load failure in words and keeps the toolbar reachable', async () => {
    listSalesOrderAllocations.mockRejectedValue(new Error('That order was rebuilt'));

    renderPanel();

    expect(await screen.findByText('The allocation could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('That order was rebuilt')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /filters/i })).toBeInTheDocument();
  });

  it('lists every line, sourced or not, with the location it comes from', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([line(), SOURCED]));

    renderPanel();

    expect(await screen.findByText('SRT382-6')).toBeInTheDocument();
    expect(screen.getByText('CB6633')).toBeInTheDocument();
    // The sourced line reads its confirmed location; the unsourced one shows a dash.
    // The STATE keeps its real label - "No source yet" is an answer, not a blank.
    expect(screen.getByText('BRW')).toBeInTheDocument();
    expect(screen.getAllByText('-')).toHaveLength(1);
    expect(screen.getByText('No source yet')).toBeInTheDocument();
    expect(screen.getByText('Sourced')).toBeInTheDocument();
  });

  it('counts what still has nowhere to come from and what is waiting on someone', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([line(), SOURCED, WAITING]));

    renderPanel();

    expect(await screen.findByText('1 without a source')).toBeInTheDocument();
    expect(screen.getByText('1 waiting on a claim')).toBeInTheDocument();
  });

  it('names the project a line was asked of, and its CS', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([WAITING]));

    renderPanel();

    expect(await screen.findByText('PRJ-000042, Aisyah')).toBeInTheDocument();
  });

  it('reads a line with an open claim as waiting, and gives it no stock location', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([WAITING]));

    renderPanel();

    expect(await screen.findByText('Waiting on a claim')).toBeInTheDocument();
    // Nothing moves while a claim is open, so the line holds no location: the only
    // "-" on screen is the location cell, not the state badge.
    expect(screen.getAllByText('-')).toHaveLength(1);
    expect(screen.queryByText('WH-KL')).not.toBeInTheDocument();
  });

  it('says nobody was asked when no source names another project', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([SOURCED]));

    renderPanel();

    expect(await screen.findByText('Nobody')).toBeInTheDocument();
  });

  it('narrows on a search and says the rest was filtered away, not that the order is empty', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([line(), SOURCED]));

    renderPanel();
    await screen.findByText('SRT382-6');

    fireEvent.change(screen.getByPlaceholderText('Search product or location'), {
      target: { value: 'CB6633' },
    });
    await waitFor(() => expect(screen.queryByText('SRT382-6')).not.toBeInTheDocument());
    expect(screen.getByText('CB6633')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search product or location'), {
      target: { value: 'nothing matches this' },
    });
    await waitFor(() => expect(screen.getByText('No line matches')).toBeInTheDocument());
    expect(
      screen.getByText('Clear the search or the state filter to see the rest.'),
    ).toBeInTheDocument();
  });

  it('filters down to one state from the toolbar', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([line(), SOURCED]));

    renderPanel();
    await screen.findByText('SRT382-6');

    openFilters();
    fireEvent.change(await screen.findByRole('combobox'), {
      target: { value: 'confirmed' },
    });

    await waitFor(() => expect(screen.queryByText('SRT382-6')).not.toBeInTheDocument());
    expect(screen.getByText('CB6633')).toBeInTheDocument();
  });

  it('offers the same read-only sources view on every line, sourced or not', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([line(), SOURCED]));

    renderPanel();

    expect(await screen.findAllByRole('button', { name: 'View sources' })).toHaveLength(2);
  });

  it('asks the ranked sources for the line the view was opened on', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([line()]));

    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'View sources' }));

    await waitFor(() => expect(listAllocationCandidates).toHaveBeenCalledWith('l1'));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('decides nothing itself: no source is chosen, changed or cleared from here', async () => {
    // Stage 1C retired the per-line writes. A button the backend no longer answers is
    // worse than no button, so none of them survives.
    listSalesOrderAllocations.mockResolvedValue(envelope([line(), SOURCED, WAITING]));

    renderPanel();
    await screen.findByText('CB6633');

    expect(screen.queryByRole('button', { name: 'Choose source' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Change' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Clear the source' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Request from/ })).not.toBeInTheDocument();
  });

  it('says where supply is composed, and offers the way there', async () => {
    listSalesOrderAllocations.mockResolvedValue(envelope([SOURCED]));

    renderPanel();

    expect(await screen.findByText('Supply is composed in Fulfilment Planning.')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /open fulfilment planning/i }),
    ).toHaveAttribute('href', '/project-sales/fulfilment-planning');
  });

  it('pins its own listing key rather than falling back to the pathname', async () => {
    renderPanel();

    await waitFor(() => expect(listingKeys.length).toBeGreaterThan(0));
    expect(listingKeys).toContain('projects.projects.view::project-so-allocations');
    expect(listingKeys).not.toContain('/project-sales/p1/sales-orders/so-1');
  });
});

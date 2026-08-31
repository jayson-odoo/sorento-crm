/**
 * P9 - the stock claims list (AC-H4), audit history since Stage 1C.
 *
 * A Borrow is now written already released, inside the confirmation of a sales order in
 * Fulfilment Planning, by the CS actor who confirms it. So this screen records what moved
 * and who moved it, and offers no answer to give: the accept and refuse routes behind those
 * buttons are gone. The two directions stay different facts and the screen keeps them
 * apart, because "nobody borrowed from us" is not "we borrowed from nobody".
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AllocationClaimRow } from '../../_shared/types/projectAllocation.types';

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
  usePathname: () => '/project-sales/stock-claims',
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

const listAllocationClaims = vi.fn();

vi.mock('../../_shared/services/projectAllocationService', () => ({
  listSalesOrderAllocations: vi.fn(),
  listAllocationCandidates: vi.fn(),
  listAllocationClaims: (...args: unknown[]) => listAllocationClaims(...args),
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

import { StockClaimsClient } from './StockClaimsClient';

/** The shape Stage 1C writes: released the moment the sales order was confirmed. */
function claim(overrides: Partial<AllocationClaimRow> = {}): AllocationClaimRow {
  return {
    id: 'c1',
    state: 'accepted',
    qty: '40',
    reason: null,
    from_project_id: 'p1',
    from_project_code: 'PRJ-000001',
    from_project_cs_name: 'Eling',
    to_project_id: 'p2',
    to_project_code: 'PRJ-000042',
    to_project_cs_name: 'Aisyah',
    product_id: 'prod-1',
    product_code: 'SRT382-6',
    product_name: 'SORENTO STAINLESS STEEL FLOOR GRATING',
    warehouse_id: 'wh-kl',
    warehouse_code: 'WH-KL',
    so_line_id: 'l1',
    sales_order_id: 'so-1',
    sales_order_ref: 'PSO-000123',
    line_no: 7,
    delivery_date: '2026-07-01',
    requested_by_name: 'Eling',
    decided_by_name: 'Eling',
    decided_at: '2026-07-20T02:00:00',
    created_at: '2026-07-20T02:00:00',
    ...overrides,
  };
}

function envelope(rows: AllocationClaimRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClaims() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StockClaimsClient />
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

/**
 * The two pickers in the popover carry the same control, told apart by their heading.
 * The heading is the paragraph, not the grid's column header button of the same name.
 */
function filterUnder(heading: string): HTMLElement {
  const label = screen
    .getAllByText(heading)
    .find((node) => node.tagName === 'P');
  const group = label?.parentElement;
  if (!group) throw new Error(`No filter group under ${heading}`);
  return within(group).getByRole('combobox');
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  listAllocationClaims.mockResolvedValue(envelope([]));
});


describe('StockClaimsClient', () => {
  it('shows skeleton rows while the history loads, not an empty list', () => {
    listAllocationClaims.mockReturnValue(new Promise(() => {}));

    const { container } = renderClaims();

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(
      screen.queryByText('No stock has been borrowed either way'),
    ).not.toBeInTheDocument();
  });

  it('says nothing has been borrowed, what would appear here, and where it starts', async () => {
    renderClaims();

    expect(
      await screen.findByText('No stock has been borrowed either way'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'A row appears here when a Borrow is confirmed in Fulfilment Planning, on either side of it.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole('link', { name: /open fulfilment planning/i })[0],
    ).toHaveAttribute('href', '/project-sales/fulfilment-planning');
  });

  it('states a load failure in words', async () => {
    listAllocationClaims.mockRejectedValue(new Error('The claims service is down'));

    renderClaims();

    expect(await screen.findByText('The stock claims could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('The claims service is down')).toBeInTheDocument();
  });

  it('opens on the whole history, both directions and every outcome', async () => {
    renderClaims();

    await waitFor(() =>
      expect(listAllocationClaims).toHaveBeenCalledWith({
        direction: 'all',
        state: undefined,
        page: 1,
        limit: 25,
      }),
    );
  });

  it('tells the two directions apart and asks the server for the one that is chosen', async () => {
    renderClaims();
    await screen.findByText('No stock has been borrowed either way');

    openFilters();
    expect(await screen.findByText('Direction')).toBeInTheDocument();

    const picker = filterUnder('Direction');
    expect(within(picker).getByText('Lent by my projects')).toBeInTheDocument();
    expect(within(picker).getByText('Borrowed by my projects')).toBeInTheDocument();

    fireEvent.change(picker, { target: { value: 'outgoing' } });

    await waitFor(() =>
      expect(listAllocationClaims).toHaveBeenCalledWith(
        expect.objectContaining({ direction: 'outgoing' }),
      ),
    );
    expect(
      await screen.findByText('Your projects have borrowed nothing'),
    ).toBeInTheDocument();
  });

  it('asks the server for one outcome when the outcome filter is set', async () => {
    renderClaims();
    await screen.findByText('No stock has been borrowed either way');

    openFilters();
    fireEvent.change(filterUnder('Outcome'), { target: { value: 'refused' } });

    await waitFor(() =>
      expect(listAllocationClaims).toHaveBeenCalledWith(
        expect.objectContaining({ state: ['refused'] }),
      ),
    );
  });

  it('drops the state filter entirely rather than sending an empty outcome', async () => {
    renderClaims();
    await screen.findByText('No stock has been borrowed either way');

    openFilters();
    fireEvent.change(filterUnder('Outcome'), { target: { value: 'accepted' } });
    await waitFor(() =>
      expect(listAllocationClaims).toHaveBeenCalledWith(
        expect.objectContaining({ state: ['accepted'] }),
      ),
    );

    fireEvent.change(filterUnder('Outcome'), { target: { value: 'all' } });

    await waitFor(() =>
      expect(listAllocationClaims).toHaveBeenCalledWith(
        expect.objectContaining({ state: undefined }),
      ),
    );
  });

  it('names who borrowed, who held it, what for, and who released it', async () => {
    listAllocationClaims.mockResolvedValue(envelope([claim()]));

    renderClaims();

    expect(await screen.findByText('PRJ-000001, Eling')).toBeInTheDocument();
    expect(screen.getByText('PRJ-000042, Aisyah')).toBeInTheDocument();
    expect(screen.getByText('SRT382-6')).toBeInTheDocument();
    expect(screen.getByText('WH-KL')).toBeInTheDocument();
    expect(screen.getByText('PSO-000123')).toBeInTheDocument();
    expect(screen.getByText('Released')).toBeInTheDocument();
    expect(screen.getByText(/^Eling on /)).toBeInTheDocument();
  });

  it('offers no answer on any row, whatever state it is in', async () => {
    // The accept and refuse routes are gone: a Borrow is written already released by the
    // CS actor who confirms the sales order, and a legacy row keeps the answer it got.
    listAllocationClaims.mockResolvedValue(
      envelope([
        claim(),
        claim({ id: 'c2', state: 'requested', decided_by_name: null, decided_at: null }),
        claim({ id: 'c3', state: 'refused', reason: 'Committed to our own hand-over.' }),
      ]),
    );

    renderClaims();

    await screen.findByText('Released');
    expect(screen.queryByRole('button', { name: 'Release' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Refuse' })).not.toBeInTheDocument();
    // A row raised before Stage 1C and never answered says so rather than offering one.
    expect(screen.getByText('Waiting')).toBeInTheDocument();
    expect(screen.getByText('Not decided')).toBeInTheDocument();
    // The reason travels with the answer, so the borrowing CS reads it without a call.
    expect(screen.getByText('Committed to our own hand-over.')).toBeInTheDocument();
  });

  it('shows a dash for an unknown value rather than a blank cell', async () => {
    listAllocationClaims.mockResolvedValue(
      envelope([
        claim({
          product_code: null,
          warehouse_code: null,
          sales_order_ref: null,
          delivery_date: null,
        }),
      ]),
    );

    renderClaims();

    expect(await screen.findByText('Not resolved')).toBeInTheDocument();
    expect(screen.getByText('No location')).toBeInTheDocument();
    expect(screen.getByText('-')).toBeInTheDocument();
    expect(screen.getByText('No date')).toBeInTheDocument();
  });

  it('narrows on a search over the projects, the product and the location', async () => {
    listAllocationClaims.mockResolvedValue(
      envelope([claim(), claim({ id: 'c2', product_code: 'CB6633', warehouse_code: 'WH-JB' })]),
    );

    renderClaims();
    await screen.findByText('SRT382-6');

    fireEvent.change(screen.getByPlaceholderText('Search project, product or location'), {
      target: { value: 'WH-JB' },
    });

    await waitFor(() => expect(screen.queryByText('SRT382-6')).not.toBeInTheDocument());
    expect(screen.getByText('CB6633')).toBeInTheDocument();
  });

  it('renders no UUID-looking id anywhere in the list', async () => {
    listAllocationClaims.mockResolvedValue(
      envelope([
        claim({
          id: 'f1e2d3c4-5678-4a90-b123-456789abcdef',
          from_project_id: 'a1b2c3d4-5678-4a90-b123-456789abcdef',
          to_project_id: 'b2c3d4e5-5678-4a90-b123-456789abcdef',
          warehouse_id: 'c3d4e5f6-5678-4a90-b123-456789abcdef',
        }),
      ]),
    );

    const { container } = renderClaims();

    await screen.findByText('SRT382-6');
    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it('pins its own listing key rather than falling back to the pathname', async () => {
    renderClaims();

    await waitFor(() => expect(listingKeys.length).toBeGreaterThan(0));
    expect(listingKeys).toContain('projects.projects.view::project-stock-claims');
    expect(listingKeys).not.toContain('/project-sales/stock-claims');
  });
});

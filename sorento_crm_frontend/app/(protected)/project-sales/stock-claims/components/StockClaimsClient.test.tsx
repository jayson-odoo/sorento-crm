/**
 * P9 - the stock claims worklist (AC-H4).
 *
 * The list opens on what is waiting on ME, because a claim nobody answers is a line that
 * never ships. The two directions are different jobs and the screen has to keep them apart:
 * "waiting on me" is a decision to take, "I asked for" is a decision to chase. Releasing is
 * one click; refusing always goes through a dialog, because a refusal with no reason sends
 * the asking CS back to the phone call the claim replaced.
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
const acceptAllocationClaim = vi.fn();
const refuseAllocationClaim = vi.fn();

vi.mock('../../_shared/services/projectAllocationService', () => ({
  listSalesOrderAllocations: vi.fn(),
  listAllocationCandidates: vi.fn(),
  confirmAllocation: vi.fn(),
  clearAllocation: vi.fn(),
  raiseAllocationClaim: vi.fn(),
  listAllocationClaims: (...args: unknown[]) => listAllocationClaims(...args),
  acceptAllocationClaim: (...args: unknown[]) => acceptAllocationClaim(...args),
  refuseAllocationClaim: (...args: unknown[]) => refuseAllocationClaim(...args),
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

function claim(overrides: Partial<AllocationClaimRow> = {}): AllocationClaimRow {
  return {
    id: 'c1',
    state: 'requested',
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
    decided_by_name: null,
    decided_at: null,
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

/** The two pickers in the popover carry the same control, told apart by their heading. */
function filterUnder(heading: string): HTMLElement {
  const group = screen.getByText(heading).parentElement;
  if (!group) throw new Error(`No filter group under ${heading}`);
  return within(group).getByRole('combobox');
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  listAllocationClaims.mockResolvedValue(envelope([]));
  acceptAllocationClaim.mockResolvedValue(claim({ state: 'accepted' }));
  refuseAllocationClaim.mockResolvedValue(claim({ state: 'refused', reason: 'Committed' }));
});

describe('StockClaimsClient', () => {
  it('offers no answer on a claim this viewer may not answer', async () => {
    // The outgoing view used to show Release and Refuse on the viewer's own request:
    // buttons the server rejects. Gated on the server's own can_answer, so the filter
    // cannot get it wrong, and "all" holds both directions at once.
    listAllocationClaims.mockResolvedValue(
      envelope([claim({ state: 'requested', can_answer: false })]),
    );
    renderClaims();

    expect(await screen.findByText('PRJ-000042, Aisyah')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Release/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Refuse/i })).toBeNull();
  });

  it('shows skeleton rows while the claims load, not an empty inbox', () => {
    listAllocationClaims.mockReturnValue(new Promise(() => {}));

    const { container } = renderClaims();

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByText('Nothing is waiting on you')).not.toBeInTheDocument();
  });

  it('says nothing is waiting, what would appear here, and where a claim starts', async () => {
    renderClaims();

    expect(await screen.findByText('Nothing is waiting on you')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Claims appear here when another project asks for stock one of yours is holding. Raise one from a sales order line under Allocation.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the pipeline' })).toHaveAttribute(
      'href',
      '/project-sales/pipeline',
    );
  });

  it('states a load failure in words', async () => {
    listAllocationClaims.mockRejectedValue(new Error('The claims service is down'));

    renderClaims();

    expect(await screen.findByText('The stock claims could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('The claims service is down')).toBeInTheDocument();
  });

  it('opens on what is waiting on me, unanswered', async () => {
    renderClaims();

    await waitFor(() =>
      expect(listAllocationClaims).toHaveBeenCalledWith({
        direction: 'incoming',
        state: ['requested'],
        page: 1,
        limit: 25,
      }),
    );
  });

  it('tells the two directions apart and asks the server for the one that is chosen', async () => {
    renderClaims();
    await screen.findByText('Nothing is waiting on you');

    openFilters();
    const direction = await screen.findByText('Direction');
    expect(direction).toBeInTheDocument();

    // Both sides of the relationship are offered, not just the inbox.
    const picker = filterUnder('Direction');
    expect(within(picker).getByText('Waiting on me')).toBeInTheDocument();
    expect(within(picker).getByText('I asked for')).toBeInTheDocument();

    fireEvent.change(picker, { target: { value: 'outgoing' } });

    await waitFor(() =>
      expect(listAllocationClaims).toHaveBeenCalledWith(
        expect.objectContaining({ direction: 'outgoing' }),
      ),
    );
  });

  it('asks the server for answered claims when the answer filter moves off waiting', async () => {
    renderClaims();
    await screen.findByText('Nothing is waiting on you');

    openFilters();
    fireEvent.change(filterUnder('Answer'), { target: { value: 'refused' } });

    await waitFor(() =>
      expect(listAllocationClaims).toHaveBeenCalledWith(
        expect.objectContaining({ state: ['refused'] }),
      ),
    );
  });

  it('drops the state filter entirely rather than sending an empty answer', async () => {
    renderClaims();
    await screen.findByText('Nothing is waiting on you');

    openFilters();
    fireEvent.change(filterUnder('Answer'), { target: { value: 'all' } });

    await waitFor(() =>
      expect(listAllocationClaims).toHaveBeenCalledWith(
        expect.objectContaining({ state: undefined }),
      ),
    );
  });

  it('names who asked, who holds it, and what for', async () => {
    listAllocationClaims.mockResolvedValue(envelope([claim()]));

    renderClaims();

    expect(await screen.findByText('PRJ-000001, Eling')).toBeInTheDocument();
    expect(screen.getByText('PRJ-000042, Aisyah')).toBeInTheDocument();
    expect(screen.getByText('SRT382-6')).toBeInTheDocument();
    expect(screen.getByText('WH-KL')).toBeInTheDocument();
    expect(screen.getByText('PSO-000123')).toBeInTheDocument();
    expect(screen.getByText('Waiting')).toBeInTheDocument();
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

  it('releases the stock on one click, with no reason asked for', async () => {
    listAllocationClaims.mockResolvedValue(envelope([claim()]));

    renderClaims();

    fireEvent.click(await screen.findByRole('button', { name: 'Release' }));

    await waitFor(() => expect(acceptAllocationClaim).toHaveBeenCalledWith('c1'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens the refusal dialog rather than refusing on the spot', async () => {
    listAllocationClaims.mockResolvedValue(envelope([claim()]));

    renderClaims();

    fireEvent.click(await screen.findByRole('button', { name: 'Refuse' }));

    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText('Refuse this claim')).toBeInTheDocument();
    expect(refuseAllocationClaim).not.toHaveBeenCalled();
  });

  it('sends the typed reason to the claim that was refused', async () => {
    listAllocationClaims.mockResolvedValue(envelope([claim()]));

    renderClaims();

    fireEvent.click(await screen.findByRole('button', { name: 'Refuse' }));
    const dialog = within(await screen.findByRole('dialog'));
    fireEvent.change(dialog.getByLabelText('Why the stock cannot be released'), {
      target: { value: 'Committed to our own hand-over in July.' },
    });
    fireEvent.click(dialog.getByRole('button', { name: 'Refuse' }));

    await waitFor(() =>
      expect(refuseAllocationClaim).toHaveBeenCalledWith(
        'c1',
        'Committed to our own hand-over in July.',
      ),
    );
  });

  it('offers no decision on a claim that was already answered, and says who answered', async () => {
    listAllocationClaims.mockResolvedValue(
      envelope([
        claim({
          state: 'refused',
          reason: 'Committed to our own hand-over in July.',
          decided_by_name: 'Aisyah',
          decided_at: '2026-07-21T02:00:00',
        }),
      ]),
    );

    renderClaims();

    expect(await screen.findByText('Answered by Aisyah')).toBeInTheDocument();
    expect(screen.getByText('Refused')).toBeInTheDocument();
    // The reason travels with the answer, so the asking CS reads it without a phone call.
    expect(
      screen.getByText('Committed to our own hand-over in July.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Release' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Refuse' })).not.toBeInTheDocument();
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

    expect(screen.getByText('CB6633')).toBeInTheDocument();
    expect(screen.queryByText('SRT382-6')).not.toBeInTheDocument();
  });

  it('pins its own listing key rather than falling back to the pathname', async () => {
    renderClaims();

    await waitFor(() => expect(listingKeys.length).toBeGreaterThan(0));
    expect(listingKeys).toContain('projects.projects.view::project-stock-claims');
    expect(listingKeys).not.toContain('/project-sales/stock-claims');
  });
});

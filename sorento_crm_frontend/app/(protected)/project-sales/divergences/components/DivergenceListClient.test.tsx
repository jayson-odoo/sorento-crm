/**
 * P8a - the management list of AutoCount differences (AC-N6).
 *
 * The point of the screen is the AGE column. A difference on the day it lands is not
 * urgent; a week of them is the stack this list exists to surface, and every row is a
 * sales order whose amendments are blocked until somebody answers it.
 *
 * The two states are opposite facts, so the empty copy has to differ: "nothing has been
 * reconciled yet" and "AutoCount agrees with everything" cannot be one sentence.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DivergenceSummary } from '../../_shared/types/soDivergence.types';

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
  usePathname: () => '/project-sales/divergences',
  useSearchParams: () => new URLSearchParams(''),
}));

// Without this the shared DataGrid sits in its column-preferences fetch forever and
// renders skeleton rows instead of data.
const listingKeys: (string | null | undefined)[] = [];
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: vi.fn(), isLoading: false };
  },
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

const listDivergences = vi.fn();

vi.mock('../../_shared/services/soDivergenceService', () => ({
  listDivergences: (...args: unknown[]) => listDivergences(...args),
  getDivergence: vi.fn(),
  ingestSalesOrderFile: vi.fn(),
  resolveDivergenceRow: vi.fn(),
  downloadCorrectiveImportFile: vi.fn(),
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

import { DivergenceListClient } from './DivergenceListClient';

function row(overrides: Partial<DivergenceSummary> = {}): DivergenceSummary {
  return {
    id: 'd1',
    project_sales_order_id: 'so-1',
    project_id: 'p1',
    project_title: 'Tuju Residences',
    sales_order_ref: 'SO397450',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO397450',
    status: 'open',
    compared_count: 52,
    agreeing_count: 48,
    differing_count: 4,
    unresolved_count: 4,
    corrective_publish_required: false,
    detected_at: '2026-08-01T02:00:00',
    resolved_at: null,
    age_days: 2,
    ...overrides,
  };
}

function envelope(rows: DivergenceSummary[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DivergenceListClient />
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
  listDivergences.mockResolvedValue(envelope([]));
});

describe('DivergenceListClient', () => {
  it('opens on what is still to reconcile rather than on everything', async () => {
    renderList();

    await waitFor(() =>
      expect(listDivergences).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'open' }),
      ),
    );
  });

  it('shows a row with its age and how much of the document differs', async () => {
    listDivergences.mockResolvedValue(envelope([row()]));
    renderList();

    expect(await screen.findByText('Tuju Residences')).toBeInTheDocument();
    expect(screen.getByText('SO397450')).toBeInTheDocument();
    expect(screen.getByText('4 of 52')).toBeInTheDocument();
    expect(screen.getByText('2 days')).toBeInTheDocument();
    expect(screen.getByText('4 unanswered')).toBeInTheDocument();
  });

  it('says amendments are blocked, because that is what an open one costs', async () => {
    listDivergences.mockResolvedValue(envelope([row()]));
    renderList();

    expect(await screen.findByText('Amendments blocked')).toBeInTheDocument();
  });

  it('reads a same-day difference as today rather than as zero days', async () => {
    listDivergences.mockResolvedValue(envelope([row({ age_days: 0 })]));
    renderList();

    expect(await screen.findByText('Today')).toBeInTheDocument();
  });

  it('does not put an age on a reconciliation that has been answered', async () => {
    listDivergences.mockResolvedValue(
      envelope([row({ status: 'resolved', age_days: 11, unresolved_count: 0 })]),
    );
    renderList();

    expect(await screen.findByText('Reconciled')).toBeInTheDocument();
    expect(screen.getByText('Answered')).toBeInTheDocument();
    expect(screen.queryByText('11 days')).not.toBeInTheDocument();
  });

  it('flags a reconciliation that still owes AutoCount a corrective file', async () => {
    listDivergences.mockResolvedValue(
      envelope([row({ status: 'resolved', corrective_publish_required: true })]),
    );
    renderList();

    expect(await screen.findByText('Corrective file to send')).toBeInTheDocument();
  });

  it('links to the reconciliation screen for that sales order', async () => {
    listDivergences.mockResolvedValue(envelope([row()]));
    renderList();

    const link = await screen.findByRole('link', { name: /reconcile/i });
    expect(link).toHaveAttribute(
      'href',
      '/project-sales/p1/sales-orders/so-1/divergence',
    );
  });

  it('offers View rather than Reconcile once it is answered', async () => {
    listDivergences.mockResolvedValue(envelope([row({ status: 'resolved' })]));
    renderList();

    expect(await screen.findByRole('link', { name: /^view$/i })).toBeInTheDocument();
  });

  it('never renders a raw id', async () => {
    listDivergences.mockResolvedValue(envelope([row()]));
    const { container } = renderList();

    await screen.findByText('Tuju Residences');
    expect(container.textContent).not.toContain('so-1');
    expect(container.textContent).not.toContain('d1');
  });

  it('says the opposite thing in each empty state, because they are opposite facts', async () => {
    renderList();

    expect(
      await screen.findByText(/autocount agrees with every published sales order/i),
    ).toBeInTheDocument();

    openFilters();
    const picker = within(screen.getByText('State').parentElement as HTMLElement).getByRole(
      'combobox',
    );
    fireEvent.change(picker, { target: { value: 'resolved' } });

    expect(
      await screen.findByText(/nothing has been reconciled yet/i),
    ).toBeInTheDocument();
  });

  it('surfaces a load failure instead of an empty list', async () => {
    listDivergences.mockRejectedValue(new Error('Backend is down'));
    renderList();

    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
    expect(screen.getByText('Backend is down')).toBeInTheDocument();
  });

  it('keys its column preferences so a user layout survives a reload', async () => {
    listDivergences.mockResolvedValue(envelope([row()]));
    renderList();

    await screen.findByText('Tuju Residences');
    expect(listingKeys).toContain('projects.projects.view::project-so-divergences');
  });
});

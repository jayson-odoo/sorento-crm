/**
 * The Plans page (PLAN-demo-followups-19aug-ladder-v2 D1, workstream D1).
 *
 * "Is the plan stored, how do I review it" - every confirmed supply decision, one row per
 * revision, cross-order. Loading / empty / error / data states, plus the state filter that
 * changes what `usePlans` is asked for.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanRow } from '../../_shared/types/fulfilmentPlanning.types';

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
  usePathname: () => '/project-sales/plans',
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

const listPlans = vi.fn();

vi.mock('../../_shared/services/plansService', () => ({
  listPlans: (...args: unknown[]) => listPlans(...args),
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
      aria-label={placeholder ?? 'State'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { PlansClient } from './PlansClient';

function row(overrides: Partial<PlanRow> = {}): PlanRow {
  return {
    project_sales_order_id: 'pso-1',
    sales_order_id: 'so-1',
    project_id: 'p1',
    so_number: 'SO397450',
    customer_name: 'Tuju Residences Sdn Bhd',
    agent_code: 'JEREMY',
    agent_label: 'Jeremy Lee',
    revision_no: 2,
    state: 'active',
    decided_by_name: 'Farah',
    decided_at: '2026-08-19T02:00:00',
    line_count: 3,
    components_summary: 'Reserve 213 · Buy 45',
    challenged_reason: null,
    ...overrides,
  };
}

function envelope(rows: PlanRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PlansClient />
    </QueryClientProvider>,
  );
}

function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  listPlans.mockResolvedValue(envelope([]));
});

describe('PlansClient', () => {
  it('opens on the active state by default', async () => {
    renderClient();

    await waitFor(() =>
      expect(listPlans).toHaveBeenCalledWith(expect.objectContaining({ state: 'active' })),
    );
  });

  it('shows the sales order, agent, revision and components summary on a seeded row', async () => {
    listPlans.mockResolvedValue(envelope([row()]));
    renderClient();

    expect(await screen.findByText('SO397450')).toBeInTheDocument();
    expect(screen.getByText('Tuju Residences Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('JEREMY')).toBeInTheDocument();
    expect(screen.getByText('Rev 2')).toBeInTheDocument();
    expect(screen.getByText('Reserve 213 · Buy 45 · 3 lines')).toBeInTheDocument();
    expect(screen.getByText('Farah')).toBeInTheDocument();
  });

  it('links Open to the project SO sheet the decision was made on', async () => {
    listPlans.mockResolvedValue(envelope([row()]));
    renderClient();

    // The project SO sheet, not the plain SCM document: it carries the supply composition
    // and Amend, which is what a row on this page is for.
    const link = await screen.findByRole('link', { name: 'Open' });
    expect(link).toHaveAttribute('href', '/project-sales/p1/sales-orders/pso-1');
  });

  it('falls back to the SCM sales order when the decision has no project registered', async () => {
    listPlans.mockResolvedValue(envelope([row({ project_id: null })]));
    renderClient();

    const link = await screen.findByRole('link', { name: 'Open' });
    expect(link).toHaveAttribute('href', '/scm/sales-orders/so-1');
  });

  it('offers a second "Open on board" action linking to the board filtered to the order', async () => {
    listPlans.mockResolvedValue(envelope([row()]));
    renderClient();

    const link = await screen.findByRole('link', { name: /open on board/i });
    expect(link).toHaveAttribute(
      'href',
      '/project-sales/fulfilment-planning?orders=SO397450',
    );
  });

  it('omits "Open on board" when the row has no sales order number to filter to', async () => {
    listPlans.mockResolvedValue(envelope([row({ so_number: null })]));
    renderClient();

    await screen.findByRole('link', { name: 'Open' });
    expect(screen.queryByRole('link', { name: /open on board/i })).not.toBeInTheDocument();
  });

  it('shows the empty state with a CTA back to Fulfilment Planning when nothing is confirmed', async () => {
    renderClient();

    expect(await screen.findByText('No plans yet')).toBeInTheDocument();
    expect(
      screen.getByText(/nothing has been confirmed yet/i),
    ).toBeInTheDocument();
    const cta = screen.getByRole('link', { name: /open fulfilment planning/i });
    expect(cta).toHaveAttribute('href', '/project-sales/fulfilment-planning');
  });

  it('surfaces a load failure instead of an empty list', async () => {
    listPlans.mockRejectedValue(new Error('Backend is down'));
    renderClient();

    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
    expect(screen.getByText('Backend is down')).toBeInTheDocument();
  });

  it('asks for a different state when the state filter changes', async () => {
    listPlans.mockResolvedValue(envelope([row({ state: 'superseded' })]));
    renderClient();

    await waitFor(() =>
      expect(listPlans).toHaveBeenCalledWith(expect.objectContaining({ state: 'active' })),
    );

    openFilters();
    const picker = screen.getByRole('combobox', { name: 'State' });
    fireEvent.change(picker, { target: { value: 'superseded' } });

    await waitFor(() =>
      expect(listPlans).toHaveBeenCalledWith(
        expect.objectContaining({ state: 'superseded' }),
      ),
    );
  });

  it('keys its column preferences so a user layout survives a reload', async () => {
    listPlans.mockResolvedValue(envelope([row()]));
    renderClient();

    await screen.findByText('SO397450');
    expect(listingKeys).toContain('projects.projects.view::project-supply-plans-v1');
  });
});

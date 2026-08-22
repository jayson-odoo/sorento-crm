/**
 * SalesAgentsList - loading / empty / error / data, and the edit path.
 *
 * The four states are asserted because a master the captain cannot read is the same
 * failure as one he cannot write: an unclassified agent must SAY it is unclassified
 * ("Not set"), never render blank.
 *
 * `useListingColumnPreferences` is mocked so DataGrid stops rendering skeletons and
 * mounts real rows under jsdom (see CLAUDE.md).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
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
  usePathname: () => '/master-data-management/sales-agents',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select
      aria-label="Demand class"
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">Not set</option>
      {props.options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const hooks = vi.hoisted(() => ({
  useSalesAgents: vi.fn(),
  useAnnotateSalesAgent: vi.fn(),
}));
vi.mock('../hooks/useSalesAgents', () => hooks);

import SalesAgentsList from './SalesAgentsList';
import type { SalesAgent } from '../types/salesAgent.types';

function agent(over: Partial<SalesAgent> = {}): SalesAgent {
  return {
    id: 'agent-1',
    sales_agent: 'SEAN III',
    description: null,
    is_active: true,
    internal_note: null,
    follow_up: false,
    person_label: 'Sean',
    demand_class: 'project',
    location_group: 'BB',
    source: 'import',
    created_at: '2026-08-01T00:00:00',
    updated_at: null,
    ...over,
  };
}

const mutateAsync = vi.fn().mockResolvedValue(undefined);

function mockList(over: Record<string, unknown> = {}) {
  hooks.useSalesAgents.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: vi.fn(),
    ...over,
  });
}

function withRows(rows: SalesAgent[]) {
  mockList({ data: { data: rows, empty: rows.length === 0, pagination: { total: rows.length, page: 1 } } });
}

beforeEach(() => {
  hooks.useSalesAgents.mockReset();
  hooks.useAnnotateSalesAgent.mockReset();
  mutateAsync.mockClear();
  hooks.useAnnotateSalesAgent.mockReturnValue({ mutateAsync, isPending: false });
});

describe('SalesAgentsList states', () => {
  it('renders the loading state', () => {
    // The header alone proves nothing (the data state has it too): what says "loading" is
    // skeletons in place of rows, and no row content.
    mockList({ isLoading: true });
    const { container } = render(<SalesAgentsList />);

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByText('SEAN III')).not.toBeInTheDocument();
    expect(screen.queryByText('No sales agents found.')).not.toBeInTheDocument();
  });

  it('renders the empty state', () => {
    withRows([]);
    render(<SalesAgentsList />);
    expect(screen.getByText('No sales agents found.')).toBeInTheDocument();
  });

  it('renders the error state', () => {
    mockList({ isError: true, error: new Error('Backend is down') });
    render(<SalesAgentsList />);
    expect(screen.getByText('Backend is down')).toBeInTheDocument();
  });

  it('renders a row per agent with the annotation columns', () => {
    withRows([
      agent(),
      agent({
        id: 'agent-2',
        sales_agent: 'LCL',
        person_label: null,
        demand_class: null,
        location_group: null,
      }),
    ]);
    render(<SalesAgentsList />);

    expect(screen.getByText('SEAN III')).toBeInTheDocument();
    expect(screen.getByText('Sean')).toBeInTheDocument();
    expect(screen.getByText('Project')).toBeInTheDocument();
    expect(screen.getByText('BB')).toBeInTheDocument();
    expect(screen.getAllByText('Import')).toHaveLength(2);
    expect(screen.getByText('LCL')).toBeInTheDocument();
    // An unclassified agent says so rather than rendering blank.
    expect(screen.getAllByText('Not set').length).toBeGreaterThanOrEqual(3);
  });

  it('offers no create and no delete', () => {
    withRows([agent()]);
    render(<SalesAgentsList />);

    expect(screen.queryByRole('button', { name: /add/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });
});

describe('SalesAgentsList editing', () => {
  it('the row edit button opens the modal on that agent and saves through the mutation', async () => {
    withRows([agent()]);
    render(<SalesAgentsList />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit SEAN III' }));
    expect(await screen.findByText('Edit SEAN III')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Person'), { target: { value: 'Sean Lim' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        id: 'agent-1',
        data: { person_label: 'Sean Lim', demand_class: 'project', location_group: 'BB' },
      }),
    );
  });
});

/**
 * SalesAgentsList - loading / empty / error / data, and the way in to a record.
 *
 * The four states are asserted because a master the captain cannot read is the same
 * failure as one he cannot write: an unclassified agent must SAY it is unclassified
 * ("Not set"), never render blank.
 *
 * Editing is no longer here. The row opens the record page, which edits in place, so the
 * pencil that used to sit at the end of every row is gone - a second door to the same
 * screen, on a row that is already a door.
 *
 * `useListingColumnPreferences` is mocked so DataGrid stops rendering skeletons and
 * mounts real rows under jsdom (see CLAUDE.md).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

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

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/sales-agents',
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  // `id` is forwarded so a real `<Label htmlFor>` (the bulk dialog's) resolves; the
  // `aria-label` default keeps the edit modal's own select findable, as it always was.
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select
      id={props.id}
      aria-label={props.id ? undefined : 'Demand class'}
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
  useBulkAnnotateSalesAgents: vi.fn(),
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
    contact_id: null,
    contact_name: null,
    source: 'import',
    created_at: '2026-08-01T00:00:00',
    updated_at: null,
    ...over,
  };
}

const bulkMutateAsync = vi.fn().mockResolvedValue({ updated: 2 });

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
  hooks.useBulkAnnotateSalesAgents.mockReset();
  push.mockReset();
  bulkMutateAsync.mockClear().mockResolvedValue({ updated: 2 });
  hooks.useBulkAnnotateSalesAgents.mockReturnValue({
    mutateAsync: bulkMutateAsync,
    isPending: false,
  });
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

describe('SalesAgentsList bulk annotation', () => {
  /**
   * The captain's first upload created 38 unclassified agent codes and every one of them
   * had to be opened, edited and saved on its own. These assert the whole path: tick rows,
   * pick a value, confirm with the COUNT on the button, and the write goes out for exactly
   * the rows that were ticked.
   */
  const TWO = [agent(), agent({ id: 'agent-2', sales_agent: 'LCL', demand_class: null })];

  function selectBoth() {
    withRows(TWO);
    render(<SalesAgentsList />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select SEAN III' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select LCL' }));
  }

  /** The dialog's own field. Scoped, because the grid carries a "Demand class" COLUMN
   *  header of the same words and an unscoped lookup finds both. */
  async function bulkInput(label: string) {
    const dialog = await screen.findByRole('alertdialog');
    return within(dialog).getByLabelText(label);
  }

  it('offers no bulk action until something is selected', () => {
    withRows(TWO);
    render(<SalesAgentsList />);
    expect(screen.queryByRole('button', { name: 'Set demand class' })).not.toBeInTheDocument();
  });

  it('sets the demand class across the selection, stating the count on the button', async () => {
    selectBoth();

    fireEvent.click(screen.getByRole('button', { name: 'Set demand class' }));
    fireEvent.change(await bulkInput('Demand class'), { target: { value: 'retail' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply to 2 agents' }));

    await waitFor(() =>
      expect(bulkMutateAsync).toHaveBeenCalledWith({
        sales_agent_ids: ['agent-1', 'agent-2'],
        demand_class: 'retail',
      }),
    );
  });

  it('sets the location group across the selection', async () => {
    selectBoth();

    fireEvent.click(screen.getByRole('button', { name: 'Set location group' }));
    fireEvent.change(await bulkInput('Location group'), { target: { value: 'BB' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply to 2 agents' }));

    await waitFor(() =>
      expect(bulkMutateAsync).toHaveBeenCalledWith({
        sales_agent_ids: ['agent-1', 'agent-2'],
        location_group: 'BB',
      }),
    );
  });

  it('sends an explicit null when the value is left empty - unset, not "leave alone"', async () => {
    selectBoth();

    fireEvent.click(screen.getByRole('button', { name: 'Set demand class' }));
    await bulkInput('Demand class');
    fireEvent.click(screen.getByRole('button', { name: 'Apply to 2 agents' }));

    await waitFor(() =>
      expect(bulkMutateAsync).toHaveBeenCalledWith({
        sales_agent_ids: ['agent-1', 'agent-2'],
        demand_class: null,
      }),
    );
  });

  it('clears the selection once the write lands, so the strip cannot describe a stale set', async () => {
    selectBoth();

    fireEvent.click(screen.getByRole('button', { name: 'Set demand class' }));
    await bulkInput('Demand class');
    fireEvent.click(screen.getByRole('button', { name: 'Apply to 2 agents' }));

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Set demand class' })).not.toBeInTheDocument(),
    );
  });

  it('keeps the dialog and the selection when the write fails', async () => {
    bulkMutateAsync.mockRejectedValueOnce(new Error('nope'));
    selectBoth();

    fireEvent.click(screen.getByRole('button', { name: 'Set demand class' }));
    fireEvent.change(await bulkInput('Demand class'), { target: { value: 'retail' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply to 2 agents' }));

    await waitFor(() => expect(bulkMutateAsync).toHaveBeenCalled());
    expect(await bulkInput('Demand class')).toHaveValue('retail');
  });
});

describe('SalesAgentsList - the row opens the record', () => {
  it('navigates when a cell other than the code is clicked', () => {
    withRows([agent()]);
    render(<SalesAgentsList />);

    fireEvent.click(screen.getByText('Sean'));

    expect(push).toHaveBeenCalledWith(
      expect.stringContaining('/master-data-management/sales-agents/agent-1'),
    );
  });

  it('carries the list query, so the record pager walks the same page', () => {
    withRows([agent()]);
    render(<SalesAgentsList />);

    fireEvent.click(screen.getByText('Sean'));

    const href = push.mock.calls[0][0] as string;
    const qs = new URLSearchParams(href.split('?')[1] ?? '');
    expect(qs.get('page')).toBe('1');
    expect(qs.get('limit')).toBe('50');
    expect(qs.get('sort')).toBe('sales_agent');
  });

  it('the code itself is a link to the record, so copy-link and middle-click work', () => {
    withRows([agent()]);
    render(<SalesAgentsList />);

    const link = screen.getByRole('link', { name: 'SEAN III' });
    expect(link).toHaveAttribute(
      'href',
      expect.stringContaining('/master-data-management/sales-agents/agent-1'),
    );

    // The anchor navigates on its own; the row handler must not fire a second push.
    fireEvent.click(link);
    expect(push).not.toHaveBeenCalled();
  });

  it('carries no pencil: the row IS the way in, and editing happens on the record', () => {
    withRows([agent()]);
    render(<SalesAgentsList />);

    expect(screen.queryByRole('button', { name: /^Edit/ })).not.toBeInTheDocument();
  });
});

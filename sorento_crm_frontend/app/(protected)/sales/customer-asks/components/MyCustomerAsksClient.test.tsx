/**
 * AC-ST209, AC-ST210: Sales > Customer asks. The SERVICE functions are mocked (never the Phase 1
 * store); the hooks and `AskTodoList` are real.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/sales/customer-asks',
  useSearchParams: () => new URLSearchParams(),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));

const setSorting = vi.fn();
let storedSorting: { id: string; desc: boolean }[] = [{ id: 'asked_at', desc: false }];
const prefsCalls: { listingKey?: string | null }[] = [];
vi.mock('@/lib/listing-column-preferences/useListingViewPreferences', () => ({
  useListingViewPreferences: (args: { listingKey?: string | null }) => {
    prefsCalls.push(args);
    return { sorting: storedSorting, setSorting, filters: null, setFilters: vi.fn(), isLoading: false };
  },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    clearable?: boolean;
    options?: { value: string; label: string }[];
  }) => (
    <select
      id={props.id}
      data-clearable={props.clearable ? 'true' : 'false'}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">-</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const getCustomerAsksTodo = vi.fn();
const listAskAgents = vi.fn();
const updateSalesAsk = vi.fn();
vi.mock('@/services/stockAskService', () => ({
  getCustomerAsksTodo: (...a: unknown[]) => getCustomerAsksTodo(...a),
  listAskAgents: (...a: unknown[]) => listAskAgents(...a),
  updateSalesAsk: (...a: unknown[]) => updateSalesAsk(...a),
}));

import { MyCustomerAsksClient } from './MyCustomerAsksClient';

const TODAY_START = '2026-09-28T16:00:00Z';

function ask(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    customer_name: `Customer ${id}`,
    contact_name: 'Ah Seng',
    product_code: `SRT-${id}`,
    product_name: null,
    quantity: 10,
    branch: 'in_stock',
    answer_summary: 'answer',
    notified_agent: true,
    notify_skip_reason: null,
    state: 'open',
    note: null,
    created_at: '2026-09-29T01:00:00Z',
    updated_at: null,
    ...over,
  };
}

function payload(over: Record<string, unknown> = {}) {
  return {
    today_start: TODAY_START,
    open: [ask('mine')],
    done_today: [],
    truncated: false,
    agent: { code: 'SEAN I', name: 'Sean Ibrahim' },
    ...over,
  };
}

const AGENTS = [
  { agent_id: 'agent-a', code: 'SEAN I', name: 'Sean Ibrahim', open: 4, needs_attention: 2 },
  { agent_id: 'agent-b', code: 'WT I', name: 'William Tan', open: 1, needs_attention: 0 },
];

beforeEach(() => {
  vi.clearAllMocks();
  storedSorting = [{ id: 'asked_at', desc: false }];
  prefsCalls.length = 0;
  getCustomerAsksTodo.mockResolvedValue(payload());
  listAskAgents.mockResolvedValue(AGENTS);
  updateSalesAsk.mockResolvedValue(ask('mine', { state: 'done' }));
});

describe('MyCustomerAsksClient (AC-ST209)', () => {
  it('renders the Customer asks header and the to-do from the query hook', async () => {
    render(<MyCustomerAsksClient />);
    expect(screen.getByRole('heading', { level: 1, name: 'Customer asks' })).toBeInTheDocument();
    expect(await screen.findByText('Customer mine')).toBeInTheDocument();
    expect(getCustomerAsksTodo).toHaveBeenCalledWith(undefined);
    expect(screen.getByTestId('ask-todo-counts')).toBeInTheDocument();
  });

  it('Done goes through updateSalesAsk, refetches and toasts', async () => {
    render(<MyCustomerAsksClient />);
    const row = (await screen.findByText('Customer mine')).closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(updateSalesAsk).toHaveBeenCalledWith('mine', { state: 'done' }));
    await waitFor(() => expect(getCustomerAsksTodo).toHaveBeenCalledTimes(2));
    expect(toast.success).toHaveBeenCalled();
  });

  it('Reopen goes through updateSalesAsk', async () => {
    getCustomerAsksTodo.mockResolvedValue(payload({ open: [], done_today: [ask('d1', { state: 'done', done_by: 'Sean' })] }));
    render(<MyCustomerAsksClient />);
    const row = (await screen.findByText('Customer d1')).closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Reopen' }));
    await waitFor(() => expect(updateSalesAsk).toHaveBeenCalledWith('d1', { state: 'open' }));
  });

  it('toasts the extracted message when the update fails', async () => {
    updateSalesAsk.mockRejectedValue(new Error('Stock ask not found'));
    render(<MyCustomerAsksClient />);
    const row = (await screen.findByText('Customer mine')).closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Stock ask not found'));
  });

  it('shows the unlinked message in place of the list when the caller has no agent', async () => {
    getCustomerAsksTodo.mockResolvedValue(payload({ open: [], agent: null }));
    render(<MyCustomerAsksClient />);
    expect(await screen.findByRole('heading', { name: 'Not linked to a sales agent' })).toBeInTheDocument();
    // A hint line under the heading, and no button (one CTA per page, none here).
    const box = screen.getByRole('heading', { name: 'Not linked to a sales agent' }).parentElement as HTMLElement;
    expect((box.textContent ?? '').replace('Not linked to a sales agent', '').trim().length).toBeGreaterThan(0);
    expect(within(box).queryByRole('button')).toBeNull();
    expect(screen.queryByText('You are not linked to a sales agent')).toBeNull();
    expect(screen.queryByTestId('ask-todo-counts')).toBeNull();
  });

  it('shows the error state when the to-do cannot be loaded', async () => {
    getCustomerAsksTodo.mockRejectedValue(new Error('Server down'));
    render(<MyCustomerAsksClient />);
    expect(await screen.findByText('Server down')).toBeInTheDocument();
  });
});

describe('MyCustomerAsksClient Agent select (AC-ST210)', () => {
  it('renders no Agent select when the agents list is empty', async () => {
    listAskAgents.mockResolvedValue([]);
    render(<MyCustomerAsksClient />);
    await screen.findByText('Customer mine');
    await waitFor(() => expect(listAskAgents).toHaveBeenCalled());
    expect(screen.queryByLabelText('Agent')).toBeNull();
  });

  it('renders a clearable Agent select with All agents first and the counts, when the list is non-empty', async () => {
    render(<MyCustomerAsksClient />);
    const select = await screen.findByLabelText('Agent');
    expect(select).toHaveAttribute('data-clearable', 'true');
    await screen.findByRole('option', { name: 'SEAN I · 4 open · 2 need attention' });
    const labels = within(select).getAllByRole('option').map((o) => o.textContent);
    expect(labels[0]).toBe('-'); // the mock's clear option
    expect(labels[1]).toBe('All agents');
  });

  it('picking an agent refetches with agent_id and clearing returns to mine', async () => {
    render(<MyCustomerAsksClient />);
    const select = await screen.findByLabelText('Agent');
    await screen.findByRole('option', { name: /WT I/ });
    fireEvent.change(select, { target: { value: 'agent-b' } });
    await waitFor(() => expect(getCustomerAsksTodo).toHaveBeenLastCalledWith('agent-b'));
    fireEvent.change(select, { target: { value: '' } });
    await waitFor(() => expect(getCustomerAsksTodo).toHaveBeenLastCalledWith(undefined));
  });

  it('All agents fetches agent_id=all and names the agent on each row', async () => {
    getCustomerAsksTodo.mockImplementation((agentId?: string) =>
      Promise.resolve(
        agentId === 'all'
          ? payload({ open: [ask('z1', { agent_code: 'WT I' })], agent: null })
          : payload(),
      ),
    );
    render(<MyCustomerAsksClient />);
    const select = await screen.findByLabelText('Agent');
    await screen.findByRole('option', { name: 'All agents' });
    fireEvent.change(select, { target: { value: 'all' } });
    await waitFor(() => expect(getCustomerAsksTodo).toHaveBeenLastCalledWith('all'));
    expect(await screen.findByText('WT I')).toBeInTheDocument();
    expect(screen.queryByText('You are not linked to a sales agent')).toBeNull();
  });
});

describe('MyCustomerAsksClient remembered sort (AC-ST120)', () => {
  it('reads the sort from the listing view preference under sales.customer_asks.view::todo', async () => {
    render(<MyCustomerAsksClient />);
    await screen.findByText('Customer mine');
    expect(prefsCalls.length).toBeGreaterThan(0);
    expect(prefsCalls.every((c) => c.listingKey === 'sales.customer_asks.view::todo')).toBe(true);
  });

  it('applies a stored customer sort on open: rows inside a day are A to Z', async () => {
    storedSorting = [{ id: 'customer', desc: false }];
    getCustomerAsksTodo.mockResolvedValue(
      payload({ open: [ask('zed', { customer_name: 'Zed Trading' }), ask('abe', { customer_name: 'Abe Trading' })] }),
    );
    render(<MyCustomerAsksClient />);
    await screen.findByText('Zed Trading');
    const names = screen.getAllByText(/Trading$/).map((n) => n.textContent);
    expect(names).toEqual(['Abe Trading', 'Zed Trading']);
    expect((screen.getByLabelText('Sort') as HTMLSelectElement).value).toBe('customer:asc');
  });

  it('changing the Sort select writes the new entry through the hook setter', async () => {
    render(<MyCustomerAsksClient />);
    await screen.findByText('Customer mine');
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'product:asc' } });
    expect(setSorting).toHaveBeenCalled();
    const arg = setSorting.mock.calls.at(-1)![0];
    const value = typeof arg === 'function' ? arg([]) : arg;
    expect(value).toEqual([{ id: 'product', desc: false }]);
  });
});

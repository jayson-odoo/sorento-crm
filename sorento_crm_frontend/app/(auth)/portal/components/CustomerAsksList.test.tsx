/**
 * Chatbot stock ask v2 S6 - the portal's Customer asks (AC-SA605). Since fix round 5 it is the
 * body of the landing's Customer asks kind: cards by default, the grid in list view, the
 * landing's own search box feeding `search`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/portal/c/ah-lim/customer_asks',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select id={props.id} value={props.value} onChange={(e) => props.onChange(e.target.value)}>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const listCustomerAsks = vi.fn();
const updateCustomerAsk = vi.fn();
vi.mock('../lib/customer-asks-service', async () => {
  const actual = await vi.importActual<typeof import('../lib/customer-asks-service')>(
    '../lib/customer-asks-service',
  );
  return {
    ...actual,
    listCustomerAsks: (...a: unknown[]) => listCustomerAsks(...a),
    updateCustomerAsk: (...a: unknown[]) => updateCustomerAsk(...a),
  };
});

import { CustomerAsksList } from './CustomerAsksList';
import { NotASalesAgentError } from '../lib/customer-asks-service';

const ROW = {
  id: 'ask-1',
  customer_name: 'Hock Lee Trading',
  contact_name: 'Ah Seng',
  product_code: 'SRT5674',
  product_name: 'Wiper Blade 24in',
  quantity: 150,
  branch: 'no_incoming',
  answer_summary: 'SRT5674 x 150: no stock and no incoming at the moment, please refer to your salesman.',
  notified_agent: true,
  notify_skip_reason: null,
  state: 'open',
  note: null,
  created_at: '2026-09-24T07:05:00',
  updated_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  listCustomerAsks.mockResolvedValue({ data: [ROW], pagination: { total: 1, page: 1, limit: 20 } });
  updateCustomerAsk.mockResolvedValue({ ...ROW, state: 'done' });
});

function Harness({ search = '', initialView = 'list' }: { search?: string; initialView?: 'list' | 'board' }) {
  const [view, setView] = React.useState<'list' | 'board'>(initialView);
  return <CustomerAsksList search={search} view={view} onViewChange={setView} />;
}

describe('CustomerAsksList', () => {
  it('renders the grid with every column in list view', async () => {
    render(<Harness />);
    await waitFor(() => expect(screen.getByText('SRT5674')).toBeInTheDocument());
    for (const header of [
      'Asked at',
      'Customer',
      'Contact',
      'Product',
      'Qty',
      'Branch',
      'Answer',
      'Notified',
      'State',
      'Note',
    ]) {
      expect(screen.getByText(header)).toBeInTheDocument();
    }
    expect(screen.getByText('Hock Lee Trading')).toBeInTheDocument();
    expect(screen.getByText('Ah Seng')).toBeInTheDocument();
    expect(screen.getByText('Sent')).toBeInTheDocument();
    expect(screen.queryByText('ask-1')).not.toBeInTheDocument();
  });

  // Owner ruling 28 Sep 2026: a chat console hand test writes asks rows too; they carry
  // a "Console" badge so they are never mistaken for a dealer's real ask.
  it('marks a console ask with a Console badge and a live ask with none', async () => {
    listCustomerAsks.mockResolvedValue({
      data: [
        { ...ROW, source: 'console' },
        { ...ROW, id: 'ask-2', product_code: 'SRT9999', source: 'live' },
      ],
      pagination: { total: 2, page: 1, limit: 20 },
    });
    render(<Harness />);
    await waitFor(() => expect(screen.getByText('SRT9999')).toBeInTheDocument());
    const badges = screen.getAllByText('Console');
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveAttribute('title', 'Written by a chat console hand test, not by a dealer');
  });

  it('shows an explicit empty state', async () => {
    listCustomerAsks.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 20 } });
    render(<Harness />);
    await waitFor(() => expect(screen.getByText('No customer asks yet')).toBeInTheDocument());
  });

  it.each(['list', 'board'] as const)('edits state and note in place (%s view)', async (initialView) => {
    render(<Harness initialView={initialView} />);
    const state = await screen.findByLabelText('State for SRT5674');
    fireEvent.change(state, { target: { value: 'done' } });
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('ask-1', { state: 'done' }));
    const note = screen.getByLabelText('Note for SRT5674');
    fireEvent.change(note, { target: { value: 'Visited, ordering Friday' } });
    fireEvent.blur(note);
    await waitFor(() =>
      expect(updateCustomerAsk).toHaveBeenCalledWith('ask-1', { note: 'Visited, ordering Friday' }),
    );
  });

  it('searches by the search it is handed, from page 1', async () => {
    const { rerender } = render(<Harness search="" />);
    await screen.findByText('SRT5674');
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <Harness search="hock" />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(listCustomerAsks).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'hock', page: 1 })),
    );
  });

  it('shows cards in board view: customer, product and qty, branch, answer', async () => {
    render(<Harness initialView="board" />);
    const card = (await screen.findByText('Hock Lee Trading')).closest('li') as HTMLElement;
    expect(card).not.toBeNull();
    expect(card.textContent).toContain('SRT5674');
    expect(card.textContent).toContain('150');
    expect(card.textContent).toContain('Ah Seng');
    expect(screen.queryByText('Asked at')).toBeNull(); // no grid header in board view
  });

  it('filters by state', async () => {
    render(<Harness />);
    await screen.findByText('SRT5674');
    fireEvent.change(screen.getByLabelText('Filter by state'), { target: { value: 'done' } });
    await waitFor(() =>
      expect(listCustomerAsks).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'done', page: 1 })),
    );
  });

  it('tells a contact who is no sales agent', async () => {
    listCustomerAsks.mockRejectedValue(new NotASalesAgentError());
    render(<Harness />);
    await waitFor(() =>
      expect(screen.getByText('Customer asks are for sales agents only.')).toBeInTheDocument(),
    );
  });
});

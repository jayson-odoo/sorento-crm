/**
 * Sales-asks-todo AC-ST117 (replaces the #1333 pins of the cards / grid body): the portal's
 * Customer asks tab body is the salesperson's to-do, `AskTodoList` fed by
 * `getCustomerAsksTodo`; `Show done` opens the #1333 done history (`state=done`) under it.
 * The service functions are mocked, never the Phase 1 mock store.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor, within } from '@testing-library/react';
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
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const getCustomerAsksTodo = vi.fn();
const listCustomerAsks = vi.fn();
const updateCustomerAsk = vi.fn();
vi.mock('../lib/customer-asks-service', async () => {
  const actual = await vi.importActual<typeof import('../lib/customer-asks-service')>(
    '../lib/customer-asks-service',
  );
  return {
    ...actual,
    getCustomerAsksTodo: (...a: unknown[]) => getCustomerAsksTodo(...a),
    listCustomerAsks: (...a: unknown[]) => listCustomerAsks(...a),
    updateCustomerAsk: (...a: unknown[]) => updateCustomerAsk(...a),
  };
});

import { CustomerAsksList } from './CustomerAsksList';
import { NotASalesAgentError } from '../lib/customer-asks-service';

const TODAY_START = '2026-09-28T16:00:00Z';

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
  source: 'live',
  created_at: '2026-09-27T05:00:00Z',
  updated_at: null,
  done_at: null,
  done_by: null,
};
const TODAY_ROW = { ...ROW, id: 'ask-2', customer_name: 'Seng Heng Motor', product_code: 'SRT9999', created_at: '2026-09-29T01:00:00Z' };
const DONE_ROW = {
  ...ROW,
  id: 'ask-3',
  customer_name: 'Cleared Trading',
  product_code: 'SRT-CLEARED',
  state: 'done',
  done_at: '2026-09-29T02:00:00Z',
  done_by: 'Agent Lim',
};

function payload(over: Record<string, unknown> = {}) {
  return { today_start: TODAY_START, open: [ROW, TODAY_ROW], done_today: [], truncated: false, ...over };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  getCustomerAsksTodo.mockResolvedValue(payload());
  listCustomerAsks.mockResolvedValue({ data: [DONE_ROW], pagination: { total: 1, page: 1, limit: 20 } });
  updateCustomerAsk.mockResolvedValue({ ...ROW, state: 'done' });
});

describe('CustomerAsksList (portal to-do body)', () => {
  it('renders the to-do from getCustomerAsksTodo: counts, groups, rows, and no grid or state filter', async () => {
    render(<CustomerAsksList search="" />);
    expect(await screen.findByText('Hock Lee Trading')).toBeInTheDocument();
    expect(getCustomerAsksTodo).toHaveBeenCalled();
    expect(screen.getByTestId('ask-todo-counts').textContent?.replace(/\s+/g, ' ')).toContain(
      'Open 2 · Needs attention 1 · Done today 0',
    );
    expect(screen.getAllByRole('heading').map((h) => h.textContent)).toEqual([
      'Needs attention',
      'Sun 27 Sep',
      'Today',
    ]);
    expect(screen.getByText('SRT5674 x 150')).toBeInTheDocument();
    expect(screen.queryByLabelText('Filter by state')).toBeNull();
    expect(screen.queryByText('Asked at')).toBeNull(); // no grid header
    expect(screen.queryByText('ask-1')).toBeNull(); // no ids in the UI
    // The done history is closed until asked for.
    expect(listCustomerAsks).not.toHaveBeenCalled();
  });

  it('Done patches the ask and refetches the to-do', async () => {
    render(<CustomerAsksList search="" />);
    const row = (await screen.findByText('Hock Lee Trading')).closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('ask-1', { state: 'done' }));
    await waitFor(() => expect(getCustomerAsksTodo).toHaveBeenCalledTimes(2));
  });

  it('Reopen and note edits go through updateCustomerAsk', async () => {
    getCustomerAsksTodo.mockResolvedValue(payload({ open: [TODAY_ROW], done_today: [DONE_ROW] }));
    render(<CustomerAsksList search="" />);
    const done = (await screen.findByText('Cleared Trading')).closest('li') as HTMLElement;
    fireEvent.click(within(done).getByRole('button', { name: 'Reopen' }));
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('ask-3', { state: 'open' }));

    const note = screen.getByLabelText('Note for SRT9999');
    fireEvent.change(note, { target: { value: 'Visited, ordering Friday' } });
    fireEvent.blur(note);
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('ask-2', { note: 'Visited, ordering Friday' }));
  });

  it('Show done toggles the done history (state=done) under the to-do', async () => {
    render(<CustomerAsksList search="" />);
    await screen.findByText('Hock Lee Trading');
    fireEvent.click(screen.getByRole('button', { name: 'Show done' }));
    await waitFor(() =>
      expect(listCustomerAsks).toHaveBeenCalledWith(expect.objectContaining({ state: 'done', page: 1 })),
    );
    expect(await screen.findByText('SRT-CLEARED')).toBeInTheDocument();
    expect(screen.getByText('Hock Lee Trading')).toBeInTheDocument(); // the to-do stays
    fireEvent.click(screen.getByRole('button', { name: 'Hide done' }));
    await waitFor(() => expect(screen.queryByText('SRT-CLEARED')).toBeNull());
  });

  it('narrows the to-do by the landing search box', async () => {
    render(<CustomerAsksList search="seng heng" />);
    expect(await screen.findByText('Seng Heng Motor')).toBeInTheDocument();
    expect(screen.queryByText('Hock Lee Trading')).toBeNull();
  });

  it('marks a console ask with a Console badge and a live ask with none', async () => {
    getCustomerAsksTodo.mockResolvedValue(payload({ open: [{ ...ROW, source: 'console' }, TODAY_ROW] }));
    render(<CustomerAsksList search="" />);
    await screen.findByText('Seng Heng Motor');
    expect(screen.getAllByText('Console')).toHaveLength(1);
  });

  it('shows the empty state when nothing is waiting', async () => {
    getCustomerAsksTodo.mockResolvedValue(payload({ open: [] }));
    render(<CustomerAsksList search="" />);
    expect(await screen.findByText('Nothing waiting')).toBeInTheDocument();
  });

  it('shows the error state when the to-do cannot be loaded', async () => {
    getCustomerAsksTodo.mockRejectedValue(new Error('Server down'));
    render(<CustomerAsksList search="" />);
    expect(await screen.findByText('Server down')).toBeInTheDocument();
  });

  it('tells a contact who is no sales agent', async () => {
    getCustomerAsksTodo.mockRejectedValue(new NotASalesAgentError());
    render(<CustomerAsksList search="" />);
    expect(await screen.findByText('Customer asks are for sales agents only.')).toBeInTheDocument();
  });

  // AC-ST121: the sort is remembered per contact in localStorage.
  describe('remembered sort', () => {
    const TWO = () =>
      payload({
        open: [
          { ...TODAY_ROW, id: 'z', customer_name: 'Zed Trading', product_code: 'SRT-Z' },
          { ...TODAY_ROW, id: 'a', customer_name: 'Abe Trading', product_code: 'SRT-A' },
        ],
      });
    const order = () => screen.getAllByText(/Trading$/).map((n) => n.textContent);

    it('applies a value stored for this contact on open', async () => {
      window.localStorage.setItem('sorento.portalAsksSort.contact-1', JSON.stringify({ id: 'customer', desc: false }));
      getCustomerAsksTodo.mockResolvedValue(TWO());
      render(<CustomerAsksList search="" contactId="contact-1" />);
      await screen.findByText('Zed Trading');
      expect(order()).toEqual(['Abe Trading', 'Zed Trading']);
      expect((screen.getByLabelText('Sort') as HTMLSelectElement).value).toBe('customer:asc');
    });

    it('ignores a value stored for another contact', async () => {
      window.localStorage.setItem('sorento.portalAsksSort.contact-2', JSON.stringify({ id: 'customer', desc: false }));
      getCustomerAsksTodo.mockResolvedValue(TWO());
      render(<CustomerAsksList search="" contactId="contact-1" />);
      await screen.findByText('Zed Trading');
      expect((screen.getByLabelText('Sort') as HTMLSelectElement).value).toBe('asked_at:asc');
    });

    it('writes the choice under the contact key when the select changes', async () => {
      getCustomerAsksTodo.mockResolvedValue(TWO());
      render(<CustomerAsksList search="" contactId="contact-1" />);
      await screen.findByText('Zed Trading');
      fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'product:asc' } });
      await waitFor(() => {
        const raw = window.localStorage.getItem('sorento.portalAsksSort.contact-1');
        expect(raw && JSON.parse(raw)).toEqual({ id: 'product', desc: false });
      });
      expect(window.localStorage.getItem('sorento.portalAsksSort.contact-2')).toBeNull();
    });
  });
});

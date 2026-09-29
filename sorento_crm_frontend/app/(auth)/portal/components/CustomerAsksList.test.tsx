/**
 * Sales-asks-todo AC-ST117 as reshaped by S3 (AC-ST304 to AC-ST308): the portal's Customer asks
 * tab body is the salesperson's to-do, `AskTodoList` fed by `getCustomerAsksTodo`, under the
 * landing's own `LandingToolbar` (Filter, Sort, list / cards toggle, no New button); a card opens
 * the conversation Drawer; `Show done` opens the #1333 done history (`state=done`) under it.
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
const gridProps = vi.hoisted(() => [] as Record<string, unknown>[]);
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn().mockResolvedValue(null),
  upsertUserListColumnConfig: vi.fn(),
  resetUserListColumnConfig: vi.fn(),
}));
vi.mock('@/components/ui/data-grid', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/ui/data-grid')>();
  return {
    ...actual,
    DataGrid: (props: Record<string, unknown>) => {
      gridProps.push(props);
      // The key asked for is recorded; rows render without the preference fetch (jsdom holds them
      // behind a skeleton while it runs).
      return <actual.DataGrid {...(props as React.ComponentProps<typeof actual.DataGrid>)} listingKey={null} />;
    },
  };
});
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const getCustomerAsksTodo = vi.fn();
const listCustomerAsks = vi.fn();
const updateCustomerAsk = vi.fn();
const getAskConversation = vi.fn();
vi.mock('../lib/customer-asks-service', async () => {
  const actual = await vi.importActual<typeof import('../lib/customer-asks-service')>(
    '../lib/customer-asks-service',
  );
  return {
    ...actual,
    getCustomerAsksTodo: (...a: unknown[]) => getCustomerAsksTodo(...a),
    listCustomerAsks: (...a: unknown[]) => listCustomerAsks(...a),
    updateCustomerAsk: (...a: unknown[]) => updateCustomerAsk(...a),
    getAskConversation: (...a: unknown[]) => getAskConversation(...a),
  };
});

import { CustomerAsksList } from './CustomerAsksList';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
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

const CONVERSATION = {
  messages: [
    { id: 1, direction: 'in', text: 'Boss, SRT5674 ada stock?', at: '2026-09-27T04:58:00' },
    { id: 2, direction: 'out', text: 'SRT5674 x 150: no stock', at: '2026-09-27T05:00:00' },
  ],
  ask_message_id: 2,
};

/** The landing's view toggle: force the cards view whatever the stored default is. */
function showCards() {
  fireEvent.click(screen.getByRole('radio', { name: 'Board view' }));
}
function showList() {
  fireEvent.click(screen.getByRole('radio', { name: 'List view' }));
}
/** Radix triggers open on a real pointerdown / pointerup / click sequence. */
async function openMenu(name: string) {
  const trigger = screen.getByRole('button', { name });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
}
const cardOf = (text: string) => screen.getByText(text).closest('li, article, [tabindex], [role="button"]') as HTMLElement;

beforeEach(() => {
  vi.clearAllMocks();
  gridProps.length = 0;
  window.localStorage.clear();
  getAskConversation.mockResolvedValue(CONVERSATION);
  getCustomerAsksTodo.mockResolvedValue(payload());
  listCustomerAsks.mockResolvedValue({ data: [DONE_ROW], pagination: { total: 1, page: 1, limit: 20 } });
  updateCustomerAsk.mockResolvedValue({ ...ROW, state: 'done' });
});

describe('CustomerAsksList (portal to-do body)', () => {
  it('renders the to-do from getCustomerAsksTodo as cards: two sections, no counts, no day headings', async () => {
    render(<CustomerAsksList search="" />);
    expect(await screen.findByText('Hock Lee Trading')).toBeInTheDocument();
    showCards();
    expect(getCustomerAsksTodo).toHaveBeenCalled();
    expect(screen.queryByTestId('ask-todo-counts')).toBeNull();
    expect(screen.getAllByRole('heading').map((h) => h.textContent)).toEqual(['Needs attention', 'Today']);
    const card = cardOf('Hock Lee Trading').textContent!.replace(/\s+/g, ' ');
    expect(card).toContain('Asked: SRT5674 x 150');
    expect(card).toContain('Answered: No stock and no incoming at the moment, please refer to your salesman.');
    expect(screen.queryByLabelText('Filter by state')).toBeNull();
    expect(screen.queryByText('ask-1')).toBeNull(); // no ids in the UI
    // The done history is closed until asked for.
    expect(listCustomerAsks).not.toHaveBeenCalled();
  });

  // AC-ST304
  it('renders the landing toolbar (Filter, Sort reading the default, view toggle) and no New button', async () => {
    render(<CustomerAsksList search="" />);
    await screen.findByText('Hock Lee Trading');
    showCards();
    expect(screen.getByRole('button', { name: 'Filter' })).toBeInTheDocument();
    // The UAC says the default reads "Created"; the asks field list (AC-ST302) names the date
    // field "Asked". Either satisfies the toolbar until the captain rules which word wins.
    expect(screen.getByRole('button', { name: 'Sort' })).toHaveTextContent(/Created|Asked/);
    expect(screen.getByLabelText('View mode')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^New/ })).toBeNull();
    expect(screen.queryByRole('link', { name: /^New/ })).toBeNull();
  });

  // AC-ST308
  it('keeps the toolbar when nothing is waiting', async () => {
    getCustomerAsksTodo.mockResolvedValue(payload({ open: [] }));
    render(<CustomerAsksList search="" />);
    expect(await screen.findByText('Nothing waiting')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Filter' })).toBeInTheDocument();
    expect(screen.getByLabelText('View mode')).toBeInTheDocument();
  });

  // AC-ST306 (portal half)
  it('list view is the DataGrid with no listing key (the portal has no user row) and Done last', async () => {
    render(<CustomerAsksList search="" />);
    await screen.findByText('Hock Lee Trading');
    showList();
    const headers = screen.getAllByRole('columnheader').map((h) => (h.textContent ?? '').trim());
    expect(headers.slice(0, 5)).toEqual(['Asked at', 'Customer', 'Contact', 'Asked', 'Answered']);
    expect(headers.at(-1)).toBe('');
    expect(gridProps.length).toBeGreaterThan(0);
    expect(gridProps.every((g) => g.listingKey === null)).toBe(true);
    const row = screen.getByText('Hock Lee Trading').closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('ask-1', { state: 'done' }));
    expect(getAskConversation).not.toHaveBeenCalled(); // the button never opens the card
  });

  it('Done patches the ask and refetches the to-do', async () => {
    render(<CustomerAsksList search="" />);
    await screen.findByText('Hock Lee Trading');
    showCards();
    fireEvent.click(within(cardOf('Hock Lee Trading')).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('ask-1', { state: 'done' }));
    await waitFor(() => expect(getCustomerAsksTodo).toHaveBeenCalledTimes(2));
    expect(getAskConversation).not.toHaveBeenCalled(); // Done never opens the card
  });

  it('Reopen goes through updateCustomerAsk', async () => {
    getCustomerAsksTodo.mockResolvedValue(payload({ open: [TODAY_ROW], done_today: [DONE_ROW] }));
    render(<CustomerAsksList search="" />);
    await screen.findByText('Cleared Trading');
    showCards();
    fireEvent.click(within(cardOf('Cleared Trading')).getByRole('button', { name: 'Reopen' }));
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('ask-3', { state: 'open' }));
  });

  // AC-ST307 (portal half): the card opens the conversation Drawer.
  it('opening a card fetches its conversation and shows it with the tagged bubble', async () => {
    render(<CustomerAsksList search="" />);
    await screen.findByText('Hock Lee Trading');
    showCards();
    fireEvent.click(screen.getByText('Hock Lee Trading'));
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(getAskConversation).toHaveBeenCalledWith('ask-1', { wholeDay: false }));
    expect(await within(dialog).findByText('Boss, SRT5674 ada stock?')).toBeInTheDocument();
    expect(within(dialog).getByText('This ask')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /Jump to message/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole('link', { name: 'Open in Conversations' })).toBeNull(); // CRM only
  });

  it('Show the whole day refetches with wholeDay true', async () => {
    render(<CustomerAsksList search="" />);
    await screen.findByText('Hock Lee Trading');
    showCards();
    fireEvent.click(screen.getByText('Hock Lee Trading'));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Show the whole day' }));
    await waitFor(() => expect(getAskConversation).toHaveBeenCalledWith('ask-1', { wholeDay: true }));
  });

  it('Save note (not blur) writes the note through updateCustomerAsk; Done at the foot clears the ask', async () => {
    render(<CustomerAsksList search="" />);
    await screen.findByText('Hock Lee Trading');
    showCards();
    fireEvent.click(screen.getByText('Hock Lee Trading'));
    const dialog = await screen.findByRole('dialog');
    const note = await within(dialog).findByLabelText('Note');
    fireEvent.change(note, { target: { value: 'Visited, ordering Friday' } });
    fireEvent.blur(note);
    expect(updateCustomerAsk).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save note' }));
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('ask-1', { note: 'Visited, ordering Friday' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('ask-1', { state: 'done' }));
  });

  it('Show done toggles the done history (state=done) under the to-do', async () => {
    render(<CustomerAsksList search="" />);
    await screen.findByText('Hock Lee Trading');
    showCards();
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

  it('shows no Console badge (or any badge) on a console ask card', async () => {
    getCustomerAsksTodo.mockResolvedValue(payload({ open: [{ ...ROW, source: 'console' }, TODAY_ROW] }));
    render(<CustomerAsksList search="" />);
    await screen.findByText('Seng Heng Motor');
    showCards();
    expect(screen.queryByText('Console')).toBeNull();
    expect(screen.queryByText('No stock, no incoming')).toBeNull();
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

  // AC-ST121 / AC-ST304: the sort is the toolbar's Sort, remembered per contact in localStorage
  // as the toolbar's own `{ key, dir }`.
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
      window.localStorage.setItem('sorento.portalAsksSort.contact-1', JSON.stringify({ key: 'customer_name', dir: 'asc' }));
      getCustomerAsksTodo.mockResolvedValue(TWO());
      render(<CustomerAsksList search="" contactId="contact-1" />);
      await screen.findByText('Zed Trading');
      showCards();
      expect(order()).toEqual(['Abe Trading', 'Zed Trading']);
      expect(screen.getByRole('button', { name: 'Sort' })).toHaveTextContent('Customer');
    });

    it('ignores a value stored for another contact', async () => {
      window.localStorage.setItem('sorento.portalAsksSort.contact-2', JSON.stringify({ key: 'customer_name', dir: 'asc' }));
      getCustomerAsksTodo.mockResolvedValue(TWO());
      render(<CustomerAsksList search="" contactId="contact-1" />);
      await screen.findByText('Zed Trading');
      showCards();
      expect(screen.getByRole('button', { name: 'Sort' })).not.toHaveTextContent('Customer');
    });

    it('re-orders inside the section and writes the choice under the contact key when Sort changes', async () => {
      getCustomerAsksTodo.mockResolvedValue(TWO());
      render(<CustomerAsksList search="" contactId="contact-1" />);
      await screen.findByText('Zed Trading');
      showCards();
      await openMenu('Sort');
      fireEvent.click(within(screen.getByRole('menu')).getByText('Customer'));
      await waitFor(() => {
        const raw = window.localStorage.getItem('sorento.portalAsksSort.contact-1');
        expect(raw && JSON.parse(raw)).toEqual({ key: 'customer_name', dir: 'asc' });
      });
      expect(order()).toEqual(['Abe Trading', 'Zed Trading']);
      expect(window.localStorage.getItem('sorento.portalAsksSort.contact-2')).toBeNull();
    });
  });
});

// AC-ST214 (FE half): the Show done history names who cleared each ask.

function doneByCells(rowText: string): string {
  const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
  const at = headers.indexOf('Done by');
  expect(at, `a "Done by" column header in ${JSON.stringify(headers)}`).toBeGreaterThan(-1);
  const row = screen.getByText(rowText).closest('tr') as HTMLElement;
  return (within(row).getAllByRole('cell')[at].textContent ?? '').trim();
}

describe('CustomerAsksList Show done history: Done by column (AC-ST214)', () => {
  it('reads "Done by <name>, <time>" or "Done" alone', async () => {
    const doneAt = '2026-09-29T02:00:00';
    listCustomerAsks.mockResolvedValue({
      data: [
        { ...DONE_ROW, id: 'h1', product_code: 'SRT-NAMED', done_at: doneAt, done_by: 'Agent Lim' },
        { ...DONE_ROW, id: 'h2', product_code: 'SRT-NONAME', done_at: doneAt, done_by: null },
      ],
      pagination: { total: 2, page: 1, limit: 20 },
    });
    render(<CustomerAsksList search="" />);
    await screen.findByText('Hock Lee Trading');
    showCards();
    fireEvent.click(screen.getByRole('button', { name: 'Show done' }));
    await screen.findByText('SRT-NAMED');
    expect(doneByCells('SRT-NAMED')).toBe(`Done by Agent Lim, ${formatDateTimeInMalaysia(doneAt)}`);
    expect(doneByCells('SRT-NONAME')).toBe('Done');
  });
});

/**
 * FILTER-MULTISELECT PR6: the portal Customer asks to-do's Customer, Contact, Product, Answer and State filters
 * take several values (OR, client-side): two picked values keep the rows of either, clearing restores all.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
const getAskConversationPage = vi.fn();
const searchAskConversation = vi.fn();
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
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
    getAskConversationPage: (...a: unknown[]) => getAskConversationPage(...a),
    searchAskConversation: (...a: unknown[]) => searchAskConversation(...a),
  };
});


class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import { CustomerAsksList as AsksBody } from './CustomerAsksList';

/**
 * The asks body takes `view` / `onViewChange` from the landing (it owns the toggle state, like
 * every other kind) and stores nothing itself. This harness plays the landing.
 */
const onViewChangeSpy = vi.fn();
function CustomerAsksList(props: { search: string; contactId?: string | null; initialView?: 'list' | 'board' }) {
  const [view, setView] = React.useState<'list' | 'board'>(props.initialView ?? 'board');
  return (
    <AsksBody
      search={props.search}
      contactId={props.contactId}
      {...({ view, onViewChange: (m: 'list' | 'board') => { onViewChangeSpy(m); setView(m); } } as object)}
    />
  );
}

const TODAY_START = '2026-09-28T16:00:00Z';
const BASE = {
  quantity: 150, branch: 'no_incoming', notified_agent: true, notify_skip_reason: null, state: 'open', note: null,
  source: 'live', created_at: '2026-09-27T05:00:00Z', updated_at: null, done_at: null, done_by: null,
};
const A = { ...BASE, id: 'ask-a', customer_name: 'ZZT Alpha Trading', contact_name: 'ZZT Contact A', product_code: 'ZZT-PA',
  product_name: 'Prod A', answer_summary: 'ZZT-PA x 150: no stock alpha' };
const B = { ...BASE, id: 'ask-b', customer_name: 'ZZT Beta Trading', contact_name: 'ZZT Contact B', product_code: 'ZZT-PB',
  product_name: 'Prod B', answer_summary: 'ZZT-PB x 150: no stock beta' };
const C = { ...BASE, id: 'ask-c', customer_name: 'ZZT Gamma Trading', contact_name: 'ZZT Contact C', product_code: 'ZZT-PC',
  product_name: 'Prod C', answer_summary: 'ZZT-PC x 150: in stock gamma', state: 'done', done_at: '2026-09-29T02:00:00Z', done_by: 'Agent' };

function onePage(): React.ReactElement {
  return <CustomerAsksList search="" initialView="list" />;
}
async function openFilter() {
  const trigger = screen.getByRole('button', { name: 'Filter' });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
}
/** The multi control offering an option whose text matches, and the values of the options to tick. */
async function multiWith(match: RegExp) {
  await waitFor(() => {
    if (!findMulti(match)) throw new Error(`no multi control offering an option matching ${match}`);
  });
  return findMulti(match) as HTMLSelectElement;
}
function findMulti(match: RegExp) {
  return screen
    .queryAllByRole('listbox')
    .find(
      (el) =>
        el.hasAttribute('multiple') && Array.from(el.querySelectorAll('option')).some((o) => match.test(o.textContent ?? '')),
    ) as HTMLSelectElement | undefined;
}
const valuesFor = (el: HTMLSelectElement, ...matches: RegExp[]) =>
  matches.map((m) => Array.from(el.querySelectorAll('option')).find((o) => m.test(o.textContent ?? ''))!.value);
const shown = (name: string) => screen.queryByText(name) !== null;

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  getAskConversation.mockResolvedValue({ messages: [], ask_message_id: 1, ask_message_ref: '1' });
  getAskConversationPage.mockResolvedValue({ items: [], has_more_older: false, has_more_newer: false, oldest_message_id: null, newest_message_id: null });
  searchAskConversation.mockResolvedValue([]);
  getCustomerAsksTodo.mockResolvedValue({ today_start: TODAY_START, open: [A, B], done_today: [C], truncated: false });
  listCustomerAsks.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 20 } });
});

// [field, option text for row A, option text for row B]
const FIELDS: [string, RegExp, RegExp][] = [
  ['Customer', /ZZT Alpha Trading/, /ZZT Beta Trading/],
  ['Contact', /ZZT Contact A/, /ZZT Contact B/],
  ['Product', /ZZT-PA/, /ZZT-PB/],
  ['Answer', /no stock alpha/i, /no stock beta/i],
];

describe('Portal customer asks - multi filters', () => {
  it.each(FIELDS)('%s is a multi control', async (_f, a) => {
    render(onePage());
    await screen.findByText('ZZT Alpha Trading');
    await openFilter();
    expect((await multiWith(a)).hasAttribute('multiple')).toBe(true);
  });

  it.each(FIELDS)('%s: two values keep the rows of either', async (_f, a, b) => {
    const user = userEvent.setup();
    render(onePage());
    await screen.findByText('ZZT Alpha Trading');
    await openFilter();
    const control = await multiWith(a);
    await user.selectOptions(control, valuesFor(control, a, b));
    await waitFor(() => expect(shown('ZZT Gamma Trading')).toBe(false));
    expect(shown('ZZT Alpha Trading')).toBe(true);
    expect(shown('ZZT Beta Trading')).toBe(true);
  });

  it.each(FIELDS)('%s: unpicking everything restores every row', async (_f, a, b) => {
    const user = userEvent.setup();
    render(onePage());
    await screen.findByText('ZZT Alpha Trading');
    await openFilter();
    const control = await multiWith(a);
    const values = valuesFor(control, a, b);
    await user.selectOptions(control, values);
    await waitFor(() => expect(shown('ZZT Gamma Trading')).toBe(false));
    await user.deselectOptions(await multiWith(a), values);
    await waitFor(() => expect(shown('ZZT Gamma Trading')).toBe(true));
  });

  it('State is a multi control: Open and Done together keep every row', async () => {
    const user = userEvent.setup();
    render(onePage());
    await screen.findByText('ZZT Alpha Trading');
    await openFilter();
    const control = await multiWith(/^open$/i);
    await user.selectOptions(control, valuesFor(control, /^open$/i, /^done$/i));
    await waitFor(() => expect(shown('ZZT Gamma Trading')).toBe(true));
    expect(shown('ZZT Alpha Trading')).toBe(true);
  });
});

/**
 * F2 / F6: the list's empty state, load error and a row. The service is mocked; the grid is real.
 * DEALER-ACCESS-NAMES (UAC `documentation/plans/contacts/dealer-access-names-14nov-acceptance-criteria.md`):
 * N1 names on chips, N2 the "My customers" switch and read-only rows, N3 the Customer filter, N5.4 the
 * Respond.io marker. `SearchableMultiSelect` is a stub input here so the Customer filter's server search can
 * be typed into; the network is `apiFetch`, mocked by URL.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { DealerAccessRow } from '@/services/dealerAccessService';
import DealerAccessView from './DealerAccessView';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  push: vi.fn(),
  replace: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  usePathname: () => '/sales/dealer-access',
  useSearchParams: () => nav.params,
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));
vi.mock('../hooks/useMyDealerCompanies', () => ({
  useMyDealerCompanies: () => ({ options: [{ value: 'SRT', label: 'Sorento' }], isLoading: false }),
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    'aria-label'?: string;
    id?: string;
    fetchOptions?: (query: string, pageIndex: number) => Promise<unknown>;
    onSearchChange?: (query: string) => void;
  }) => (
    <input
      id={props.id}
      aria-label={props['aria-label']}
      onChange={(e) => {
        void props.fetchOptions?.(e.target.value, 0);
        props.onSearchChange?.(e.target.value);
      }}
    />
  ),
}));

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  apiFetch: api.apiFetch,
}));

const svc = vi.hoisted(() => ({ getPeople: vi.fn(), getAccounts: vi.fn() }));
vi.mock('@/services/dealerAccessService', async (orig) => ({
  ...(await orig<typeof import('@/services/dealerAccessService')>()),
  getPeople: svc.getPeople,
  getAccounts: svc.getAccounts,
}));

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** A people row in the new shape; invented names and codes. */
function row(over: Partial<DealerAccessRow> & Record<string, unknown> = {}): DealerAccessRow {
  return {
    contact_id: 'c1',
    name: 'Ali Test',
    phone: '+60 12-000 0001',
    company: 'SRT',
    company_name: 'Sorento',
    accounts: [
      { id: 'a1', code: '300-A004', name: 'Kedai Test Satu', link_id: 'l1', mine: true },
      { id: 'b1', code: '300-B001', name: 'Kedai Lain', mine: false },
    ],
    access: 'employee',
    owner_tag: null,
    editable: true,
    in_respond: true,
    ...over,
  } as unknown as DealerAccessRow;
}

function page(rows: DealerAccessRow[]) {
  return { data: rows, pagination: { page: 1, limit: 50, total: rows.length } };
}

/** The labels of a row's actions menu; [] when the row has no menu at all. */
function menuLabelsFor(name: string): string[] {
  const trigger = screen.queryByRole('button', { name: `${name} actions` });
  if (!trigger) return [];
  fireEvent.pointerDown(trigger, new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
  return screen.queryAllByRole('menuitem').map((m) => (m.textContent || '').trim());
}

function lastPeopleParams(): Record<string, unknown> {
  const calls = svc.getPeople.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
}

/** Opens the Filters popover; the existing Access filter being there proves it is open. */
async function openFilters() {
  fireEvent.click(screen.getByRole('button', { name: /filter/i }));
  await screen.findByLabelText('Access');
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.params = new URLSearchParams();
  svc.getAccounts.mockResolvedValue([]);
  api.apiFetch.mockImplementation(async (url: string) => {
    if (String(url).includes('/respond')) return json({ respond: 'ok', respond_error: null });
    return json([]);
  });
});

describe('DealerAccessView', () => {
  it('renders the empty state with a heading and hint and the one Add people button', async () => {
    svc.getPeople.mockResolvedValue({ data: [], pagination: { page: 1, limit: 50, total: 0 } });
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getByText('No people have access yet')).toBeTruthy());
    expect(screen.getByText('Add people to give them access to your accounts.')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /add people/i })).toHaveLength(1);
  });

  it('renders the load error with Retry', async () => {
    svc.getPeople.mockRejectedValue(new Error('boom'));
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getByText('Could not load people')).toBeTruthy());
    expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy();
  });

  // Was: "renders a person with the owner tag and the other-account hint". N2.6 removes the hint.
  it('N2.6 renders a person with the owner tag and no "also another account" text', async () => {
    svc.getPeople.mockResolvedValue(
      page([row({ access: 'owner', owner_tag: 'Sorento Business Owner' })]),
    );
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getByText('Ali Test')).toBeTruthy());
    expect(screen.getByText('Sorento Business Owner')).toBeTruthy();
    expect(screen.queryByText(/also another account/i)).toBeNull();
  });
});

/**
 * jsdom measures every width as 0, so `PillOverflow` would fold every chip after the first into "+N". The N1
 * tests stub the widths the way `components/common/PillOverflow.test.tsx` does: each pill 100px, the row 2000px,
 * so every chip renders.
 */
const originalOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
const originalClientWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');

function stubChipWidths() {
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get(this: HTMLElement) {
      return (this.textContent ?? '').startsWith('+') ? 60 : 100;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() {
      return 2000;
    },
  });
}

function restoreChipWidths() {
  if (originalOffsetWidth) Object.defineProperty(HTMLElement.prototype, 'offsetWidth', originalOffsetWidth);
  if (originalClientWidth) Object.defineProperty(HTMLElement.prototype, 'clientWidth', originalClientWidth);
}

describe('DealerAccessView - DEALER-ACCESS-NAMES chips', () => {
  beforeEach(stubChipWidths);
  afterEach(restoreChipWidths);

  it('N1.1 chips read the customer names, with the code as the hover title', async () => {
    svc.getPeople.mockResolvedValue(page([row()]));
    render(<DealerAccessView />);
    const chips = await screen.findByTestId('dealer-accounts-c1:SRT');
    expect(within(chips).getAllByText('Kedai Test Satu').length).toBeGreaterThan(0);
    expect(within(chips).getAllByText('Kedai Lain').length).toBeGreaterThan(0);
    expect(within(chips).queryByText('300-A004')).toBeNull();
    expect(within(chips).queryByText('300-B001')).toBeNull();
    expect(chips.querySelector('[title="300-A004"]')).not.toBeNull();
    expect(chips.querySelector('[title="300-B001"]')).not.toBeNull();
  });

  it('N1.2 two chips of one row with the same name read "Name (code)", a unique name reads just "Name"', async () => {
    svc.getPeople.mockResolvedValue(
      page([
        row({
          accounts: [
            { id: 'a1', code: '300-A004', name: 'Kedai Test Satu', link_id: 'l1', mine: true },
            { id: 'a9', code: '300-A009', name: 'Kedai Test Satu', link_id: 'l9', mine: true },
            { id: 'b1', code: '300-B001', name: 'Kedai Lain', mine: false },
          ] as unknown as DealerAccessRow['accounts'],
        }),
      ]),
    );
    render(<DealerAccessView />);
    const chips = await screen.findByTestId('dealer-accounts-c1:SRT');
    expect(within(chips).getAllByText('Kedai Test Satu (300-A004)').length).toBeGreaterThan(0);
    expect(within(chips).getAllByText('Kedai Test Satu (300-A009)').length).toBeGreaterThan(0);
    expect(within(chips).getAllByText('Kedai Lain').length).toBeGreaterThan(0);
    expect(within(chips).queryByText('Kedai Lain (300-B001)')).toBeNull();
  });
});

describe('DealerAccessView - DEALER-ACCESS-NAMES', () => {

  it('N2.5 a non-editable row has no Edit and no Unlink action', async () => {
    svc.getPeople.mockResolvedValue(
      page([
        row({
          contact_id: 'c2',
          name: 'Chong Test',
          editable: false,
          accounts: [{ id: 'b1', code: '300-B001', name: 'Kedai Lain', mine: false }] as unknown as DealerAccessRow['accounts'],
        }),
      ]),
    );
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getByText('Chong Test')).toBeTruthy());
    const labels = menuLabelsFor('Chong Test');
    expect(labels.some((l) => /^edit/i.test(l))).toBe(false);
    expect(labels.some((l) => /unlink/i.test(l))).toBe(false);
  });

  it('N2.5 clicking a non-editable row opens the dialog read-only (fields shown, no Save)', async () => {
    svc.getPeople.mockResolvedValue(
      page([
        row({
          contact_id: 'c2',
          name: 'Chong Test',
          phone: '+60 12-000 0002',
          editable: false,
          accounts: [{ id: 'b1', code: '300-B001', name: 'Kedai Lain', mine: false }] as unknown as DealerAccessRow['accounts'],
        }),
      ]),
    );
    render(<DealerAccessView />);
    fireEvent.click(await screen.findByText('Chong Test'));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('+60 12-000 0002')).toBeTruthy();
    expect(within(dialog).getAllByText(/Kedai Lain/).length).toBeGreaterThan(0);
    expect(within(dialog).queryByRole('button', { name: 'Save' })).toBeNull();
  });

  it('N2.8 Unlink offers only my own accounts', async () => {
    svc.getPeople.mockResolvedValue(page([row()]));
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getByText('Ali Test')).toBeTruthy());
    const unlinks = menuLabelsFor('Ali Test').filter((l) => /unlink/i.test(l));
    expect(unlinks).toHaveLength(1);
    expect(unlinks[0]).toMatch(/Kedai Test Satu/);
    expect(unlinks[0]).not.toMatch(/Kedai Lain/);
  });

  it('N2.7 the "My customers" switch is on by default and the list is asked with mine', async () => {
    svc.getPeople.mockResolvedValue(page([row()]));
    render(<DealerAccessView />);
    await waitFor(() => expect(svc.getPeople).toHaveBeenCalled());
    expect(lastPeopleParams().mine).toBe(true);
    await openFilters();
    const toggle = await screen.findByRole('switch', { name: /my customers/i });
    expect(toggle.getAttribute('aria-checked')).toBe('true');
  });

  it('N2.7 turning "My customers" off asks with mine false and writes mine=0 to the address bar; Clear all turns it on', async () => {
    const replaceState = vi.spyOn(window.history, 'replaceState');
    const pushState = vi.spyOn(window.history, 'pushState');
    svc.getPeople.mockResolvedValue(page([row()]));
    render(<DealerAccessView />);
    await openFilters();
    fireEvent.click(await screen.findByRole('switch', { name: /my customers/i }));

    await waitFor(() => expect(lastPeopleParams().mine).toBe(false));
    const written = [
      ...nav.replace.mock.calls,
      ...nav.push.mock.calls,
      ...replaceState.mock.calls.map((c) => [c[2]]),
      ...pushState.mock.calls.map((c) => [c[2]]),
    ].map((c) => String(c[0] ?? ''));
    expect(written.some((u) => /[?&]mine=0(&|$)/.test(u))).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: /my customers/i }).getAttribute('aria-checked')).toBe('true'),
    );
    await waitFor(() => expect(lastPeopleParams().mine).toBe(true));
    replaceState.mockRestore();
    pushState.mockRestore();
  });

  it('N2.7 mine=0 in the address bar opens the list with the switch off', async () => {
    nav.params = new URLSearchParams('mine=0');
    svc.getPeople.mockResolvedValue(page([row()]));
    render(<DealerAccessView />);
    await waitFor(() => expect(svc.getPeople).toHaveBeenCalled());
    expect(lastPeopleParams().mine).toBe(false);
    await openFilters();
    const toggle = await screen.findByRole('switch', { name: /my customers/i });
    expect(toggle.getAttribute('aria-checked')).toBe('false');
  });

  it('N3.3 the Filters popover has a Customer filter that asks the server as the user types', async () => {
    svc.getPeople.mockResolvedValue(page([row()]));
    render(<DealerAccessView />);
    await openFilters();
    const customer = await screen.findByLabelText('Customer');
    fireEvent.change(customer, { target: { value: 'kedai' } });
    await waitFor(() =>
      expect(
        api.apiFetch.mock.calls.some(
          ([url]) => /\/sales\/dealer-access\/customers\?/.test(String(url)) && /query=kedai/.test(String(url)),
        ),
      ).toBe(true),
    );
  });

  it('N5.4 a row not in Respond.io says so and offers "Try again in Respond.io" that calls the retry route', async () => {
    svc.getPeople.mockResolvedValue(page([row({ in_respond: false })]));
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getAllByText('Not in Respond.io yet').length).toBeGreaterThan(0));
    const trigger = screen.getByRole('button', { name: 'Ali Test actions' });
    fireEvent.pointerDown(trigger, new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /try again in respond\.io/i }));
    await waitFor(() =>
      expect(
        api.apiFetch.mock.calls.some(
          ([url, init]) =>
            /\/sales\/dealer-access\/people\/c1\/respond$/.test(String(url)) &&
            String((init as RequestInit | undefined)?.method).toUpperCase() === 'POST',
        ),
      ).toBe(true),
    );
  });

  it('N5.4 a non-editable row not in Respond.io shows the marker but no Try again action', async () => {
    svc.getPeople.mockResolvedValue(
      page([row({ contact_id: 'c2', name: 'Chong Test', editable: false, in_respond: false })]),
    );
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getAllByText('Not in Respond.io yet').length).toBeGreaterThan(0));
    expect(menuLabelsFor('Chong Test').some((l) => /try again/i.test(l))).toBe(false);
  });

  it('N5.4 a row in Respond.io shows no marker', async () => {
    svc.getPeople.mockResolvedValue(page([row({ in_respond: true })]));
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getByText('Ali Test')).toBeTruthy());
    expect(screen.queryByText('Not in Respond.io yet')).toBeNull();
  });
});

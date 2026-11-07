/**
 * SALES-INSIGHTS-P2 (tester-first RED): the leaderboard's basis / View by / drill / channel / target /
 * Open as report / remembered setup. Names follow the UAC ids.
 *
 * URL contract pinned here (every key is optional; absent = the default):
 *   basis=invoiced|delivered|ordered|outstanding   by=person|customer|product|brand|category|channel
 *   period=this_month|last_month|this_quarter|ytd|custom|all_open   from=YYYY-MM-DD&to=YYYY-MM-DD (custom)
 *   company=<value>  brand=<id>... category=<id>...  channel=<value>...
 *   person=<label>...  customer=<id>...  product=<id>...   (drill chips)
 *   customer_label=<name>  product_label=<name>             (chip captions, one each)
 * Every state change goes through router.push (so Back works); the mocked router below updates the mocked
 * useSearchParams, so the view re-reads its own URL.
 */
import React, { useSyncExternalStore } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { periodRange } from './leaderboardFormat';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const nav = vi.hoisted(() => {
  let search = '';
  const listeners = new Set<() => void>();
  return {
    pushes: [] as string[],
    urls: [] as string[],
    get search() {
      return search;
    },
    set(url: string) {
      search = url.includes('?') ? url.split('?')[1].split('#')[0] : '';
      listeners.forEach((l) => l());
    },
    subscribe(l: () => void) {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
});
const paramsCache = new Map<string, URLSearchParams>();
vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/leaderboard',
  useRouter: () => ({
    push: (url: string) => {
      nav.pushes.push(url);
      nav.urls.push(url);
      nav.set(url);
    },
    replace: (url: string) => {
      nav.urls.push(url);
      nav.set(url);
    },
  }),
  useSearchParams: () => {
    const s = useSyncExternalStore(nav.subscribe, () => nav.search, () => nav.search);
    if (!paramsCache.has(s)) paramsCache.set(s, new URLSearchParams(s));
    return paramsCache.get(s)!;
  },
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ id, value, onChange, options = [] }: {
    id?: string; value?: string; onChange?: (v: string) => void; options?: Array<{ value: string; label: string }>;
  }) => (
    <select aria-label={id} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      <option value="" />
      {options.map((o) => (<option key={o.value} value={o.value}>{o.label}</option>))}
    </select>
  ),
}));
// A native stand-in, keyed by the control's id (lb-brand, lb-category, lb-channel).
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ id, value, onChange, options = [] }: {
    id?: string; value: string[]; onChange: (v: string[]) => void; options?: Array<{ value: string; label: string }>;
  }) => (
    <div data-testid={id}>
      {options.map((o) => (
        <label key={o.value}>
          <input
            type="checkbox"
            aria-label={o.label}
            checked={value.includes(o.value)}
            onChange={(e) => onChange(e.target.checked ? [...value, o.value] : value.filter((v) => v !== o.value))}
          />
          {o.label}
        </label>
      ))}
    </div>
  ),
}));

type Loose = Record<string, unknown>;
const state = vi.hoisted(() => ({
  calls: [] as Loose[],
  respond: (() => undefined) as (params: Loose) => unknown,
  options: {} as unknown,
}));
vi.mock('@/hooks/useSalesLeaderboardQuery', () => ({
  useSalesLeaderboardQuery: (params: Loose) => {
    state.calls.push(params);
    return { data: state.respond(params), isLoading: false, isFetching: false, isError: false, error: null };
  },
  useSalesLeaderboardOptionsQuery: () => ({ data: state.options }),
}));

import LeaderboardView from './LeaderboardView';

const CHANNELS_INVOICED = [
  ['dealer', 'Dealer'], ['project', 'Project team'], ['other', 'Other'], ['set_apart', 'Set apart'],
  ['mixed', 'Mixed sales order types'], ['type_not_set', 'Sales order type not set'], ['no_sales_order', 'No sales order'],
].map(([value, label]) => ({ value, label }));
const CHANNELS_ORDER = [['dealer', 'Dealer'], ['project', 'Project team'], ['other', 'Other']].map(
  ([value, label]) => ({ value, label }),
);
const optionsFor = (can: boolean) => ({
  companies: [{ value: 'SOR', label: 'Sorento' }],
  brands: [{ value: 'b1', label: 'SORENTO' }],
  categories: [{ value: 'c1', label: 'Lighting' }],
  channels: { invoiced: CHANNELS_INVOICED, delivered: CHANNELS_ORDER, ordered: CHANNELS_ORDER, outstanding: CHANNELS_ORDER },
  can: { invoiced: can, delivered: can, ordered: can, outstanding: can },
});

const base = (rank: number, name: string, extra: Loose = {}): Loose => ({
  rank, name, keys: [], amount: 1000 - rank, qty: 0, prev_amount: 100, change_pct: 10.0, customers: 3, products: 5, ...extra,
});
const personRow = (rank: number, person: string, extra: Loose = {}) =>
  base(rank, person, { person, codes: [person], is_me: false, target: null, ...extra });
const customerRow = (rank: number, name: string, keys: string[], code: string, companies: string[]) =>
  base(rank, name, { keys, code, companies });
const productRow = (rank: number, name: string, key: string) =>
  base(rank, name, { keys: [key], brand: 'SORENTO', category: 'Lighting', qty: 12 });

function board(by: string, rows: Loose[], extra: Loose = {}): Loose {
  return {
    basis: 'invoiced', by,
    date_from: '2026-10-01', date_to: '2026-10-31', previous_from: '2026-09-01', previous_to: '2026-09-30',
    as_of: '2026-11-04T03:10:00',
    total: { amount: 5000, qty: 0, prev_amount: 4000, change_pct: 25.0, customers: 9, products: 9 },
    no_agent_amount: 0, rows, me: null, can_drill_others: true, ...extra,
  };
}

const last = () => state.calls[state.calls.length - 1];
const lastUrl = () => new URL(nav.urls[nav.urls.length - 1], 'http://x');
const trs = (container: HTMLElement) => [...container.querySelectorAll('tbody tr')] as HTMLElement[];
const rowOf = (container: HTMLElement, text: string) => trs(container).find((tr) => tr.textContent?.includes(text))!;
const clickTab = (name: string) => {
  const tab = screen.getByRole('tab', { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
};
const standard = (params: Loose): unknown => {
  const by = String(params.by ?? 'person');
  if (by === 'customer') return board(by, [customerRow(1, 'ACME SDN BHD', ['c-1', 'c-2'], '304-R015', ['SOR', 'SOT'])]);
  if (by === 'product') return board(by, [productRow(1, 'AC-EXP-006', 'p-1')]);
  if (by === 'brand') return board(by, [base(1, 'SORENTO', { keys: ['b1'] })]);
  if (by === 'channel') return board(by, [base(1, 'Dealer', { keys: [], key: 'dealer' })]);
  return board('person', [personRow(1, 'LCL'), personRow(2, 'SEAN')]);
};

beforeEach(() => {
  nav.set('');
  nav.pushes = [];
  nav.urls = [];
  state.calls = [];
  state.respond = standard;
  state.options = optionsFor(true);
  window.localStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('P2-2 URL round trip', () => {
  it('reads basis, by, period, filters and chips from the URL into the query', () => {
    nav.set('?basis=delivered&by=customer&period=last_month&company=SOR&brand=b1&category=c1&channel=dealer&person=LCL');
    render(<LeaderboardView />);
    const range = periodRange('last_month');
    expect(last()).toMatchObject({
      basis: 'delivered', by: 'customer', date_from: range.from, date_to: range.to,
      previous_from: range.previousFrom, previous_to: range.previousTo,
      company: ['SOR'], brand: ['b1'], category: ['c1'], channel: ['dealer'], person: ['LCL'],
    });
    expect(screen.getByRole('button', { name: 'Delivered' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'Invoiced' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByRole('button', { name: 'Last month' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('tab', { name: 'Customer' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('Sales person: LCL')).toBeTruthy();
  });

  it('with no URL state it opens on Invoiced, Sales person, This month, no chips', () => {
    render(<LeaderboardView />);
    expect(last()).toMatchObject({ basis: 'invoiced', by: 'person', date_from: periodRange('this_month').from });
    expect(screen.getByRole('button', { name: 'Invoiced' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'This month' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.queryByRole('button', { name: /^Remove / })).toBeNull();
  });

  it('a custom range comes back from from= and to=', () => {
    nav.set('?period=custom&from=2026-10-01&to=2026-10-15');
    render(<LeaderboardView />);
    expect(last()).toMatchObject({ date_from: '2026-10-01', date_to: '2026-10-15' });
    expect(last().previous_from).toBeUndefined();
  });

  it('writes basis, by and period to the URL with push, keeping the drill chips (P1-2)', () => {
    nav.set('?by=customer&person=LCL&brand=b1');
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Ordered' }));
    expect(nav.pushes.length).toBe(1);
    let sp = lastUrl().searchParams;
    expect(sp.get('basis')).toBe('ordered');
    expect(sp.get('by')).toBe('customer');
    expect(sp.getAll('person')).toEqual(['LCL']);
    expect(sp.getAll('brand')).toEqual(['b1']);

    clickTab('Product');
    sp = lastUrl().searchParams;
    expect(sp.get('by')).toBe('product');
    expect(sp.get('basis')).toBe('ordered');
    expect(sp.getAll('person')).toEqual(['LCL']);

    fireEvent.click(screen.getByRole('button', { name: 'Last month' }));
    sp = lastUrl().searchParams;
    expect(sp.get('period')).toBe('last_month');
    expect(sp.get('by')).toBe('product');
    expect(last()).toMatchObject({ basis: 'ordered', by: 'product', person: ['LCL'] });
  });
});

describe('P2-1 / P2-3 drill and chip removal', () => {
  it('drills person -> customer -> product with chips, by a pushed URL each (Back returns)', () => {
    const { container } = render(<LeaderboardView />);
    fireEvent.click(rowOf(container, 'LCL'));
    expect(nav.pushes.length).toBe(1);
    expect(last()).toMatchObject({ by: 'customer', person: ['LCL'] });
    expect(screen.getByText('Sales person: LCL')).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Customer' }).getAttribute('aria-selected')).toBe('true');

    fireEvent.click(rowOf(container, 'ACME SDN BHD'));
    expect(nav.pushes.length).toBe(2);
    expect(last()).toMatchObject({ by: 'product', person: ['LCL'], customer: ['c-1', 'c-2'] });
    expect(screen.getByText('Customer: ACME SDN BHD')).toBeTruthy();
    expect(lastUrl().searchParams.get('customer_label')).toBe('ACME SDN BHD');
    expect(screen.getByText('Sales person: LCL')).toBeTruthy();
  });

  it('a product row drills to the Customer view under a product chip', () => {
    nav.set('?by=product');
    const { container } = render(<LeaderboardView />);
    fireEvent.click(rowOf(container, 'AC-EXP-006'));
    expect(last()).toMatchObject({ by: 'customer', product: ['p-1'] });
    expect(screen.getByText('Product: AC-EXP-006')).toBeTruthy();
  });

  it('a brand row and a channel row drill to Customer as a brand / channel filter', () => {
    nav.set('?by=brand');
    const first = render(<LeaderboardView />);
    fireEvent.click(rowOf(first.container, 'SORENTO'));
    expect(last()).toMatchObject({ by: 'customer', brand: ['b1'] });
    first.unmount();

    nav.set('?by=channel');
    const second = render(<LeaderboardView />);
    fireEvent.click(rowOf(second.container, 'Dealer'));
    expect(last()).toMatchObject({ by: 'customer', channel: ['dealer'] });
  });

  it('the chip x removes that chip and keeps the others', () => {
    nav.set('?by=product&person=LCL&customer=c-1&customer_label=ACME%20SDN%20BHD');
    render(<LeaderboardView />);
    expect(last()).toMatchObject({ person: ['LCL'], customer: ['c-1'] });
    fireEvent.click(screen.getByRole('button', { name: 'Remove Customer: ACME SDN BHD' }));
    expect(screen.queryByText('Customer: ACME SDN BHD')).toBeNull();
    expect(screen.getByText('Sales person: LCL')).toBeTruthy();
    expect(last().customer ?? []).toEqual([]);
    expect(last().person).toEqual(['LCL']);
    expect(lastUrl().searchParams.has('customer')).toBe(false);
    expect(lastUrl().searchParams.get('person')).toBe('LCL');
  });
});

describe('P6 who sees what', () => {
  it('P6-2 the non-person View by tabs are absent without options.can[basis]', () => {
    state.options = optionsFor(false);
    render(<LeaderboardView />);
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Sales person']);
  });

  it('P6-2 the tabs follow the basis: can.delivered only', () => {
    state.options = { ...optionsFor(false), can: { invoiced: false, delivered: true, ordered: false, outstanding: false } };
    render(<LeaderboardView />);
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Sales person']);
    fireEvent.click(screen.getByRole('button', { name: 'Delivered' }));
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'Sales person', 'Customer', 'Product', 'Brand', 'Category', 'Channel',
    ]);
  });

  it('P1-1 with can[basis] all six tabs show, in order', () => {
    render(<LeaderboardView />);
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'Sales person', 'Customer', 'Product', 'Brand', 'Category', 'Channel',
    ]);
  });

  it('P6-1 without can_drill_others only the caller\'s own row is clickable', () => {
    state.respond = () => board('person', [personRow(1, 'LCL'), personRow(2, 'JENNIFER', { is_me: true })], {
      can_drill_others: false, me: { person: 'JENNIFER', rank: 2 },
    });
    const { container } = render(<LeaderboardView />);
    const own = rowOf(container, 'JENNIFER');
    const other = rowOf(container, 'LCL');
    expect(own.getAttribute('data-drill')).toBe('true');
    expect(other.getAttribute('data-drill')).toBeNull();

    fireEvent.click(other);
    expect(nav.pushes.length).toBe(0);
    fireEvent.click(own);
    expect(nav.pushes.length).toBe(1);
    expect(last()).toMatchObject({ by: 'customer', person: ['JENNIFER'] });
  });

  it('P6-2 with can_drill_others every row is clickable', () => {
    const { container } = render(<LeaderboardView />);
    expect(trs(container).every((tr) => tr.getAttribute('data-drill') === 'true')).toBe(true);
  });
});

describe('P1-4 columns', () => {
  it('Customer rows: name with the code underneath, and a Companies column', () => {
    nav.set('?by=customer');
    const { container } = render(<LeaderboardView />);
    const row = rowOf(container, 'ACME SDN BHD');
    expect(within(row).getByText('ACME SDN BHD')).toBeTruthy();
    expect(within(row).getByText('304-R015')).toBeTruthy();
    expect(within(row).getByText('SOR, SOT')).toBeTruthy();
    expect(screen.getAllByText('Companies').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('leaderboard-podium')).toBeNull();
  });

  it('Product rows: Brand, Category and Qty columns', () => {
    nav.set('?by=product');
    const { container } = render(<LeaderboardView />);
    for (const header of ['Brand', 'Category', 'Qty']) expect(screen.getAllByText(header).length).toBeGreaterThan(0);
    const row = rowOf(container, 'AC-EXP-006');
    expect(within(row).getByText('SORENTO')).toBeTruthy();
    expect(within(row).getByText('Lighting')).toBeTruthy();
    expect(within(row).getByText('12')).toBeTruthy();
  });

  it('Sales person view keeps the podium and has no Companies / Brand columns', () => {
    render(<LeaderboardView />);
    expect(screen.getByTestId('leaderboard-podium')).toBeTruthy();
    expect(screen.queryByText('Companies')).toBeNull();
  });
});

describe('P4 Target column', () => {
  const target = (extra: Loose) => ({
    target_no: 'T-1', basis: 'ordered', period_from: '2026-01-01', period_to: '2026-12-31',
    target_amount: 1000000, achieved_amount: 720000, achieved_pct: 72, like_for_like: false, ...extra,
  });

  it('P4-1 labels the figure with the target\'s own period and basis', () => {
    state.respond = () => board('person', [personRow(1, 'LCL', { target: target({}) }), personRow(2, 'SEAN')]);
    const { container } = render(<LeaderboardView />);
    expect(screen.getAllByText('Target').length).toBeGreaterThan(0);
    expect(within(rowOf(container, 'LCL')).getByText(/^72(\.0)?% of 2026, ordered$/)).toBeTruthy();
  });

  it('P4-1 like for like shows the percentage alone', () => {
    state.respond = () => board('person', [
      personRow(1, 'LCL', {
        target: target({ basis: 'invoiced', period_from: '2026-10-01', period_to: '2026-10-31', achieved_pct: 85.5, like_for_like: true }),
      }),
    ]);
    const { container } = render(<LeaderboardView />);
    const row = rowOf(container, 'LCL');
    expect(within(row).getByText(/^85\.5%$/)).toBeTruthy();
    expect(row.textContent).not.toMatch(/% of /);
  });

  it('P4-2 a row without a target is blank while another row has one', () => {
    state.respond = () => board('person', [personRow(1, 'LCL', { target: target({}) }), personRow(2, 'SEAN')]);
    const { container } = render(<LeaderboardView />);
    expect(rowOf(container, 'SEAN').textContent).not.toMatch(/% of /);
  });

  it('P4-2 the column is absent while no row has a target', () => {
    render(<LeaderboardView />);
    expect(screen.queryByText('Target')).toBeNull();
  });

  it('P4-1 the Target column belongs to the Sales person view only', () => {
    nav.set('?by=customer');
    state.respond = () => board('customer', [
      { ...customerRow(1, 'ACME SDN BHD', ['c-1'], '304-R015', ['SOR']), target: target({}) },
    ]);
    render(<LeaderboardView />);
    expect(screen.queryByText('Target')).toBeNull();
  });
});

describe('P9 Channel', () => {
  it('P9-1 the Channel options switch with the basis: seven on Invoiced, three on the order bases', () => {
    render(<LeaderboardView />);
    const boxes = () => within(screen.getByTestId('lb-channel')).getAllByRole('checkbox');
    expect(boxes().map((b) => b.getAttribute('aria-label'))).toEqual(CHANNELS_INVOICED.map((o) => o.label));
    expect(boxes().map((b) => b.getAttribute('aria-label'))).toContain('No sales order');

    fireEvent.click(screen.getByRole('button', { name: 'Ordered' }));
    expect(boxes().map((b) => b.getAttribute('aria-label'))).toEqual(['Dealer', 'Project team', 'Other']);
  });

  it('P9-1 ticking a channel filters the query and the URL', () => {
    render(<LeaderboardView />);
    fireEvent.click(within(screen.getByTestId('lb-channel')).getByLabelText('Dealer'));
    expect(last().channel).toEqual(['dealer']);
    expect(lastUrl().searchParams.getAll('channel')).toEqual(['dealer']);
  });
});

describe('P10 Basis switch', () => {
  it('P10-1 the four basis chips', () => {
    render(<LeaderboardView />);
    for (const name of ['Invoiced', 'Delivered', 'Ordered', 'Undelivered orders']) {
      expect(screen.getByRole('button', { name })).toBeTruthy();
    }
    expect(screen.queryByRole('button', { name: 'All open' })).toBeNull();
  });

  it('P10-2 Undelivered opens on All open: no dates sent, chip pressed', () => {
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Undelivered orders' }));
    expect(lastUrl().searchParams.get('basis')).toBe('outstanding');
    expect(lastUrl().searchParams.get('period')).toBe('all_open');
    expect(last().basis).toBe('outstanding');
    expect(last().date_from).toBeUndefined();
    expect(last().date_to).toBeUndefined();
    expect(last().previous_from).toBeUndefined();
    expect(screen.getByRole('button', { name: 'All open' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('P10-2 a period chip narrows Undelivered to dates', () => {
    nav.set('?basis=outstanding&period=all_open');
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Last month' }));
    expect(last().date_from).toBe(periodRange('last_month').from);
    expect(screen.getByRole('button', { name: 'All open' }).getAttribute('aria-pressed')).toBe('false');
  });

  it('P10-2 opened by URL with no period, Undelivered still defaults to All open', () => {
    nav.set('?basis=outstanding');
    render(<LeaderboardView />);
    expect(last().date_from).toBeUndefined();
    expect(screen.getByRole('button', { name: 'All open' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('P10-2 "vs last period" cells are blank on Undelivered', () => {
    nav.set('?basis=outstanding');
    state.respond = () => ({
      ...board('person', [personRow(1, 'LCL', { prev_amount: null, change_pct: null })], {
        basis: 'outstanding', date_from: null, date_to: null, previous_from: null, previous_to: null,
      }),
      total: { amount: 5000, qty: 0, prev_amount: null, change_pct: null, customers: 9, products: 9 },
    });
    const { container } = render(<LeaderboardView />);
    const headers = [...container.querySelectorAll('thead th')].map((th) => th.textContent?.trim());
    const col = headers.findIndex((h) => h === 'vs last period');
    expect(col).toBeGreaterThanOrEqual(0);
    const cells = [...rowOf(container, 'LCL').querySelectorAll('td')];
    expect(cells[col].textContent?.trim()).toBe('');
  });
});

describe('P5-1 Open as report', () => {
  const seedOf = (href: string) => {
    const url = new URL(href, 'http://x');
    return { url, seed: JSON.parse(url.searchParams.get('seed') ?? 'null') };
  };

  it('links to Sales & outstanding with the tab, the rows = by, the period and every filter', () => {
    nav.set('?basis=invoiced&by=customer&period=custom&from=2026-10-01&to=2026-10-31&brand=b1&category=c1&channel=dealer&person=LCL&product=p-1');
    render(<LeaderboardView />);
    const href = screen.getByRole('link', { name: 'Open as report' }).getAttribute('href')!;
    const { url, seed } = seedOf(href);
    expect(url.pathname).toBe('/sales/sales-and-outstanding');
    expect(url.searchParams.get('tab')).toBe('invoiced');
    expect(seed.pivot).toEqual({ rows: 'customer', cols: 'all', measures: ['amount', 'qty'] });
    expect(seed.params.period).toEqual({ kind: 'custom', from: '2026-10-01', to: '2026-10-31' });
    expect(seed.params.brand).toEqual(['b1']);
    expect(seed.params.category).toEqual(['c1']);
    expect(seed.params.channel).toEqual(['dealer']);
    expect(seed.params.sales_person).toEqual(['LCL']);
    expect(seed.params.product).toEqual(['p-1']);
  });

  it.each([
    ['person', 'sales_person'], ['customer', 'customer'], ['product', 'product'], ['brand', 'brand'], ['category', 'category'],
  ])('by=%s seeds the pivot rows with %s', (by, rows) => {
    nav.set(`?by=${by}&period=custom&from=2026-10-01&to=2026-10-31`);
    render(<LeaderboardView />);
    const { seed } = seedOf(screen.getByRole('link', { name: 'Open as report' }).getAttribute('href')!);
    expect(seed.pivot.rows).toBe(rows);
  });

  it.each([
    ['invoiced', 'invoiced'], ['delivered', 'delivered'], ['ordered', 'ordered'], ['outstanding', 'undelivered'],
  ])('basis %s opens the %s tab', (basis, tab) => {
    nav.set(`?basis=${basis}`);
    render(<LeaderboardView />);
    const { url } = seedOf(screen.getByRole('link', { name: 'Open as report' }).getAttribute('href')!);
    expect(url.searchParams.get('tab')).toBe(tab);
  });

  it('Undelivered all open sends no period', () => {
    nav.set('?basis=outstanding&period=all_open');
    render(<LeaderboardView />);
    const { seed } = seedOf(screen.getByRole('link', { name: 'Open as report' }).getAttribute('href')!);
    expect(seed.params.period).toBeUndefined();
  });
});

describe('P3-1 Open in Top selling items', () => {
  it('shows on Invoiced + Product only, carrying period, brand and category', () => {
    nav.set('?basis=invoiced&by=product&period=custom&from=2026-10-01&to=2026-10-31&brand=b1&category=c1');
    render(<LeaderboardView />);
    const href = screen.getByRole('link', { name: 'Open in Top selling items' }).getAttribute('href')!;
    const url = new URL(href, 'http://x');
    expect(url.pathname).toBe('/sales/top-selling-items');
    const seed = JSON.parse(url.searchParams.get('seed') ?? 'null');
    expect(seed.params.period).toEqual({ kind: 'custom', from: '2026-10-01', to: '2026-10-31' });
    expect(seed.params.brand).toEqual(['b1']);
    expect(seed.params.category).toEqual(['c1']);
  });

  it.each([
    ['?basis=invoiced&by=customer'],
    ['?basis=delivered&by=product'],
    ['?basis=outstanding&by=product'],
    ['?basis=invoiced&by=person'],
  ])('is absent on %s', (search) => {
    nav.set(search);
    render(<LeaderboardView />);
    expect(screen.queryByRole('link', { name: 'Open in Top selling items' })).toBeNull();
  });
});

describe('P11-1 remember the last setup', () => {
  it('restores the last basis / view / filters when the URL has none', () => {
    const first = render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Ordered' }));
    clickTab('Customer');
    fireEvent.click(within(screen.getByTestId('lb-channel')).getByLabelText('Dealer'));
    first.unmount();

    nav.set('');
    render(<LeaderboardView />);
    expect(last()).toMatchObject({ basis: 'ordered', by: 'customer', channel: ['dealer'] });
    expect(screen.getByRole('button', { name: 'Ordered' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('a URL with state wins over the remembered setup', () => {
    const first = render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Delivered' }));
    first.unmount();

    nav.set('?basis=ordered');
    render(<LeaderboardView />);
    expect(last().basis).toBe('ordered');
  });

  it('still renders when the browser refuses storage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    const { container } = render(<LeaderboardView />);
    expect(trs(container).length).toBeGreaterThan(0);
    expect(last()).toMatchObject({ basis: 'invoiced', by: 'person' });
    expect(() => fireEvent.click(screen.getByRole('button', { name: 'Delivered' }))).not.toThrow();
    expect(last().basis).toBe('delivered');
  });
});

describe('review fix: a view of a thousand rows pages client-side', () => {
  it('shows one page of the grid and the rest behind the pager and Show more', () => {
    nav.set('?by=customer');
    state.respond = () =>
      board('customer', Array.from({ length: 120 }, (_, i) => customerRow(i + 1, `CUSTOMER ${i + 1}`, [`c-${i}`], `C-${i}`, ['SOR'])));
    const { container } = render(<LeaderboardView />);
    expect(trs(container).length).toBe(50);
    expect(screen.getByText(/1 - 50 of 120/)).toBeTruthy();
    const list = screen.getByTestId('leaderboard-list');
    expect(list.querySelectorAll('button').length).toBe(50 + 1);
    fireEvent.click(within(list).getByRole('button', { name: /Show more \(70\)/ }));
    expect(list.querySelectorAll('button').length).toBe(100 + 1);
  });
});

describe('fix round 2', () => {
  const threePeople = () =>
    board('person', [personRow(1, 'LCL'), personRow(2, 'SEAN'), personRow(3, 'JUSTIN'), personRow(4, 'JIMMY')]);

  it('1: a podium card drills like its row (button, data-drill, same handler)', () => {
    state.respond = threePeople;
    render(<LeaderboardView />);
    const card = screen.getByTestId('leaderboard-podium-1');
    expect(card.tagName).toBe('BUTTON');
    expect(card.getAttribute('data-drill')).toBe('true');
    fireEvent.click(card);
    expect(last()).toMatchObject({ by: 'customer', person: ['LCL'] });
  });

  it('1: a podium card is not clickable when its row would not be', () => {
    state.respond = () =>
      board('person', [personRow(1, 'LCL'), personRow(2, 'JENNIFER', { is_me: true }), personRow(3, 'SEAN')], {
        can_drill_others: false,
      });
    render(<LeaderboardView />);
    const other = screen.getByTestId('leaderboard-podium-1');
    expect(other.tagName).not.toBe('BUTTON');
    expect(other.getAttribute('data-drill')).toBeNull();
    fireEvent.click(other);
    expect(nav.pushes.length).toBe(0);
    const own = screen.getByTestId('leaderboard-podium-2');
    expect(own.getAttribute('data-drill')).toBe('true');
    fireEvent.click(own);
    expect(last()).toMatchObject({ by: 'customer', person: ['JENNIFER'] });
  });

  it('3: switching basis keeps the period; leaving Undelivered restores the last dated period', () => {
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Last month' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delivered' }));
    expect(lastUrl().searchParams.get('period')).toBe('last_month');
    fireEvent.click(screen.getByRole('button', { name: 'Undelivered orders' }));
    expect(lastUrl().searchParams.get('period')).toBe('all_open');
    fireEvent.click(screen.getByRole('button', { name: 'Ordered' }));
    expect(lastUrl().searchParams.get('period')).toBe('last_month');
    expect(screen.getByRole('button', { name: 'Last month' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('3: a custom range survives the same round trip', () => {
    nav.set('?period=custom&from=2026-10-01&to=2026-10-15');
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Undelivered orders' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delivered' }));
    const sp = lastUrl().searchParams;
    expect([sp.get('period'), sp.get('from'), sp.get('to')]).toEqual(['custom', '2026-10-01', '2026-10-15']);
  });

  it('6: removing a chip returns to that chip\'s own view', () => {
    nav.set('?by=product&person=LCL&customer=c-1&customer_label=ACME%20SDN%20BHD&product=p-1&product_label=AC-1');
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Remove Sales person: LCL' }));
    expect(lastUrl().searchParams.get('by')).toBe('person');
    fireEvent.click(screen.getByRole('button', { name: 'Remove Customer: ACME SDN BHD' }));
    expect(lastUrl().searchParams.get('by')).toBe('customer');
    fireEvent.click(screen.getByRole('button', { name: 'Remove Product: AC-1' }));
    expect(lastUrl().searchParams.get('by')).toBe('product');
  });

  it('7a: a header sorts on the server: the URL and the query carry sort and dir', () => {
    render(<LeaderboardView />);
    const header = () => within(document.querySelector('thead') as HTMLElement).getByRole('button', { name: 'Invoiced net (RM)' });
    fireEvent.click(header());
    expect([lastUrl().searchParams.get('sort'), lastUrl().searchParams.get('dir')]).toEqual(['amount', 'asc']);
    expect(last()).toMatchObject({ sort: 'amount', dir: 'asc' });
    fireEvent.click(header());
    expect(last()).toMatchObject({ sort: 'amount', dir: 'desc' });
  });

  it('7a: the URL sort comes back into the query, and the default is rank asc', () => {
    nav.set('?by=customer&sort=name&dir=desc');
    const first = render(<LeaderboardView />);
    expect(last()).toMatchObject({ sort: 'name', dir: 'desc' });
    first.unmount();
    nav.set('?by=customer');
    render(<LeaderboardView />);
    expect(last()).toMatchObject({ sort: 'rank', dir: 'asc' });
  });

  it('7a: the grid keeps the server order (no client sort)', () => {
    nav.set('?by=customer&sort=name&dir=desc');
    state.respond = () =>
      board('customer', [customerRow(2, 'ZED', ['c-2'], 'Z', ['SOR']), customerRow(1, 'ALPHA', ['c-1'], 'A', ['SOR'])]);
    const { container } = render(<LeaderboardView />);
    expect(trs(container).map((tr) => tr.textContent?.includes('ZED'))).toEqual([true, false]);
  });

  it('7b: Company is a multi select held as a list in the URL and the query', () => {
    nav.set('?company=SOR&company=MCH');
    state.options = { ...optionsFor(true), companies: [{ value: 'SOR', label: 'SOR' }, { value: 'MCH', label: 'MCH' }] };
    render(<LeaderboardView />);
    expect(last()).toMatchObject({ company: ['SOR', 'MCH'] });
    fireEvent.click(within(screen.getByTestId('lb-company')).getByLabelText('MCH'));
    expect(lastUrl().searchParams.getAll('company')).toEqual(['SOR']);
  });

  it('7c: Open as report and Top selling items carry the companies', () => {
    nav.set('?by=product&company=SOR&company=MCH&period=custom&from=2026-10-01&to=2026-10-31');
    render(<LeaderboardView />);
    for (const name of ['Open as report', 'Open in Top selling items']) {
      const url = new URL(screen.getByRole('link', { name }).getAttribute('href')!, 'http://x');
      expect(JSON.parse(url.searchParams.get('seed')!).params.company).toEqual(['SOR', 'MCH']);
    }
  });

  it('8b: the blank row is a line under the grid, not a ranked row', () => {
    nav.set('?by=product');
    state.respond = () =>
      board('product', [productRow(1, 'AC-EXP-006', 'p-1')], {
        blank: { name: '(no product)', amount: 38000, qty: 4, prev_amount: 0, change_pct: null },
      });
    const { container } = render(<LeaderboardView />);
    expect(trs(container).length).toBe(1);
    const line = screen.getByTestId('leaderboard-blank');
    expect(line.textContent).toContain('(no product)');
    expect(line.textContent).toContain('38,000.00');
  });

  it('8b: no blank line when there is none', () => {
    render(<LeaderboardView />);
    expect(screen.queryByTestId('leaderboard-blank')).toBeNull();
  });
});

describe('fix round 3', () => {
  const header = (name: string) =>
    within(document.querySelector('thead') as HTMLElement).getByRole('button', { name });
  const sortOf = () => [lastUrl().searchParams.get('sort'), lastUrl().searchParams.get('dir')];

  it.each([
    ['', 'Rank', 'rank'],
    ['?by=customer', '#', 'rank'],
    ['', 'Sales person', 'name'],
    ['?by=customer', 'Customer', 'name'],
    ['?by=customer', 'Companies', 'companies'],
    ['?by=product', 'Item', 'name'],
    ['?by=product', 'Brand', 'brand'],
    ['?by=product', 'Category', 'category'],
    ['?by=brand', 'Brand', 'name'],
    ['?by=channel', 'Channel', 'name'],
  ])('7: %s the %s header sorts by %s on the server and toggles the direction', (search, title, key) => {
    nav.set(search);
    render(<LeaderboardView />);
    fireEvent.click(header(title));
    // The default order is rank ascending, so its own header's first click is descending.
    const first = key === 'rank' ? 'desc' : 'asc';
    expect(sortOf()).toEqual([key, first]);
    fireEvent.click(header(title));
    // Rank's second click is its way back to the default order (rank ascending, no URL param).
    expect(sortOf()).toEqual(key === 'rank' ? [null, null] : [key, 'desc']);
  });

  it('7: the person Codes header sorts by codes', () => {
    state.respond = () => board('person', [personRow(1, 'LCL', { codes: ['LCL', 'LCL2'] })]);
    render(<LeaderboardView />);
    fireEvent.click(header('Codes'));
    expect(sortOf()).toEqual(['codes', 'asc']);
  });

  it('3: Undelivered carries the last dated period in the URL, and Invoiced reads it back', () => {
    nav.set('?basis=outstanding&period=all_open&back_period=last_month');
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Invoiced' }));
    expect(lastUrl().searchParams.get('period')).toBe('last_month');
    expect(lastUrl().searchParams.has('back_period')).toBe(false);
  });

  it('3: Last month -> Undelivered -> remount from that URL -> Invoiced is still Last month', () => {
    const first = render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Last month' }));
    fireEvent.click(screen.getByRole('button', { name: 'Undelivered orders' }));
    const url = lastUrl();
    expect(url.searchParams.get('back_period')).toBe('last_month');
    first.unmount();
    nav.set(url.search);
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Invoiced' }));
    expect(lastUrl().searchParams.get('period')).toBe('last_month');
  });

  it('3: a custom range is carried as back_from / back_to', () => {
    nav.set('?period=custom&from=2026-10-01&to=2026-10-15');
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Undelivered orders' }));
    const sp = lastUrl().searchParams;
    expect([sp.get('back_period'), sp.get('back_from'), sp.get('back_to')]).toEqual(['custom', '2026-10-01', '2026-10-15']);
  });

  it('minor: a custom range equal to a chip\'s own range selects that chip', () => {
    const r = periodRange('last_month');
    nav.set(`?period=custom&from=${r.from}&to=${r.to}`);
    render(<LeaderboardView />);
    expect(screen.getByRole('button', { name: 'Last month' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'Custom' }).getAttribute('aria-pressed')).toBe('false');
  });
});

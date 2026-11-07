import type { LeaderboardBasis, LeaderboardBy, LeaderboardParams } from '@/services/salesLeaderboardService';
import { periodRange, type PeriodKind } from './leaderboardFormat';

/** SALES-INSIGHTS-P2: the whole board setup lives in the URL (basis, by, period, filters, drill chips). */
export type Period = PeriodKind | 'all_open';

export const BASES: { value: LeaderboardBasis; label: string }[] = [
  { value: 'invoiced', label: 'Invoiced' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'ordered', label: 'Ordered' },
  { value: 'outstanding', label: 'Undelivered orders' },
];

export const VIEWS: { value: LeaderboardBy; label: string }[] = [
  { value: 'person', label: 'Sales person' },
  { value: 'customer', label: 'Customer' },
  { value: 'product', label: 'Product' },
  { value: 'brand', label: 'Brand' },
  { value: 'category', label: 'Category' },
  { value: 'channel', label: 'Channel' },
];

const PERIODS: Period[] = ['this_month', 'last_month', 'this_quarter', 'ytd', 'custom', 'all_open'];

export interface Setup {
  basis: LeaderboardBasis;
  by: LeaderboardBy;
  period: Period;
  from: string;
  to: string;
  company: string[];
  sort: string;
  dir: 'asc' | 'desc';
  brand: string[];
  category: string[];
  channel: string[];
  person: string[];
  customer: string[];
  product: string[];
  customerLabel: string;
  productLabel: string;
}

const KEYS = ['basis', 'by', 'period', 'from', 'to', 'sort', 'dir', 'company', 'brand', 'category', 'channel', 'person', 'customer', 'product'];

export const hasSetupKeys = (sp: URLSearchParams) => KEYS.some((key) => sp.has(key));

export const defaultPeriod = (basis: LeaderboardBasis): Period => (basis === 'outstanding' ? 'all_open' : 'this_month');

export function parseSetup(sp: URLSearchParams): Setup {
  const basis = BASES.find((b) => b.value === sp.get('basis'))?.value ?? 'invoiced';
  const by = VIEWS.find((v) => v.value === sp.get('by'))?.value ?? 'person';
  const asked = PERIODS.find((p) => p === sp.get('period'));
  const period = !asked || (asked === 'all_open' && basis !== 'outstanding') ? defaultPeriod(basis) : asked;
  return {
    basis,
    by,
    period,
    from: sp.get('from') ?? '',
    to: sp.get('to') ?? '',
    company: sp.getAll('company'),
    sort: sp.get('sort') ?? 'rank',
    dir: sp.get('dir') === 'desc' ? 'desc' : 'asc',
    brand: sp.getAll('brand'),
    category: sp.getAll('category'),
    channel: sp.getAll('channel'),
    person: sp.getAll('person'),
    customer: sp.getAll('customer'),
    product: sp.getAll('product'),
    customerLabel: sp.get('customer_label') ?? '',
    productLabel: sp.get('product_label') ?? '',
  };
}

export function serializeSetup(s: Setup): string {
  const sp = new URLSearchParams({ basis: s.basis, by: s.by, period: s.period });
  if (s.period === 'custom') {
    if (s.from) sp.set('from', s.from);
    if (s.to) sp.set('to', s.to);
  }
  if (s.sort !== 'rank' || s.dir !== 'asc') {
    sp.set('sort', s.sort);
    sp.set('dir', s.dir);
  }
  for (const key of ['company', 'brand', 'category', 'channel', 'person', 'customer', 'product'] as const) {
    for (const value of s[key]) sp.append(key, value);
  }
  if (s.customer.length && s.customerLabel) sp.set('customer_label', s.customerLabel);
  if (s.product.length && s.productLabel) sp.set('product_label', s.productLabel);
  return sp.toString();
}

/** The remembered setup: filters and view, never a drill (a drilled view could be one the user may not reopen). */
export function rememberable(s: Setup): string {
  const drilled = s.person.length + s.customer.length + s.product.length > 0;
  return serializeSetup({
    ...s, by: drilled ? 'person' : s.by, sort: 'rank', dir: 'asc',
    person: [], customer: [], product: [], customerLabel: '', productLabel: '',
  });
}

/** The window of a setup: undefined dates on "All open" (nothing to ask), no previous window on Custom. */
export function windowOf(s: Setup): { from?: string; to?: string; previousFrom?: string; previousTo?: string } {
  if (s.period === 'all_open') return {};
  if (s.period === 'custom') return { from: s.from, to: s.to };
  return periodRange(s.period);
}

export const isRunnable = (s: Setup): boolean => {
  if (s.period === 'all_open') return true;
  const w = windowOf(s);
  return Boolean(w.from && w.to && w.to >= w.from);
};

export function queryParams(s: Setup): LeaderboardParams {
  const w = windowOf(s);
  return {
    basis: s.basis,
    by: s.by,
    date_from: w.from,
    date_to: w.to,
    // No compare on Undelivered; the backend ignores it there.
    previous_from: s.basis === 'outstanding' ? undefined : w.previousFrom,
    previous_to: s.basis === 'outstanding' ? undefined : w.previousTo,
    company: s.company,
    sort: s.sort,
    dir: s.dir,
    brand: s.brand,
    category: s.category,
    channel: s.channel,
    person: s.person,
    customer: s.customer,
    product: s.product,
  };
}

const PIVOT_ROWS: Record<LeaderboardBy, string> = {
  person: 'sales_person',
  customer: 'customer',
  product: 'product',
  brand: 'brand',
  category: 'category',
  channel: 'channel',
};
const REPORT_TAB: Record<LeaderboardBasis, string> = {
  invoiced: 'invoiced',
  delivered: 'delivered',
  ordered: 'ordered',
  outstanding: 'undelivered',
};

function seedParams(s: Setup, keys: Array<'company' | 'brand' | 'category' | 'channel' | 'person' | 'customer' | 'product'>) {
  const params: Record<string, unknown> = {};
  const w = windowOf(s);
  if (w.from && w.to) params.period = { kind: 'custom', from: w.from, to: w.to };
  for (const key of keys) {
    if (s[key].length) params[key === 'person' ? 'sales_person' : key] = s[key];
  }
  return params;
}

/** Sales & outstanding on the basis's tab, the board's grouping as the pivot rows and every filter as a param. */
export function reportHref(s: Setup): string {
  const seed = {
    params: seedParams(s, ['company', 'brand', 'category', 'channel', 'person', 'customer', 'product']),
    pivot: { rows: PIVOT_ROWS[s.by], cols: 'all', measures: ['amount', 'qty'] },
  };
  return `/sales/sales-and-outstanding?tab=${REPORT_TAB[s.basis]}&seed=${encodeURIComponent(JSON.stringify(seed))}`;
}

/** Top selling items on the same period, brand and category (Invoiced, Product view only). */
export function topSellingHref(s: Setup): string {
  const seed = { params: seedParams(s, ['company', 'brand', 'category']) };
  return `/sales/top-selling-items?seed=${encodeURIComponent(JSON.stringify(seed))}`;
}

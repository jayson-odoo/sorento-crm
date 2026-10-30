/**
 * FILTER-MULTISELECT PR4: a class label containing a comma ("Sink, Undermount") on the Spec verification worklist
 * reaches the service intact (never split), is written to the page URL whole and read back whole, and an older
 * single-value link still reads back.
 */
import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action',
  dismissDeferredToast: vi.fn(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissionSet: new Set(['master_data.products.edit']) }),
}));
const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  usePathname: () => '/master-data-management/spec-verification',
  useSearchParams: () => nav.params,
}));
const getSpecVerificationWorklist = vi.hoisted(() => vi.fn());
vi.mock('../services/specVerificationService', () => ({
  getSpecVerificationWorklist: (...a: unknown[]) => getSpecVerificationWorklist(...a),
  verifySpecBulk: vi.fn(),
  unverifySpecBulk: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import SpecVerificationList from './SpecVerificationList';

const ROW = {
  product_id: 'id-WC100', product_code: 'WC100', product_name: 'Product WC100', class_label: 'ZZT Sink',
  brand_name: 'Sorento', is_discontinued: false,
  coverage: { have: 1, applicable: 2, items: [] }, open_exceptions: 0, values_hash: 'hash-WC100',
  verification: {
    state: 'unverified', verified_by_name: null, verified_at: null, invalidated_at: null,
    invalidated_reason: null, invalidated_by_name: null, invalidated_diff: null,
  },
};
const ENVELOPE = {
  data: [ROW], pagination: { total: 1, page: 1, limit: 25 },
  summary: { total: 1, verified: 0, needs_reverify: 0, unverified: 1 },
  classes: ['Sink, Undermount', 'ZZT Tap', 'ZZT Basin'],
};

const lastParams = () => {
  const calls = getSpecVerificationWorklist.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}
const selected = (el: HTMLSelectElement) => Array.from(el.selectedOptions, (o) => o.value).sort();
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SpecVerificationList />
    </QueryClientProvider>,
  );
  await screen.findByText('Product WC100');
  await user.click(filtersButton());
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.params = new URLSearchParams();
  getSpecVerificationWorklist.mockResolvedValue(ENVELOPE);
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

const CLASS = 'Sink, Undermount';
const asList = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : v == null || v === '' ? [] : [String(v)]);
const urlClassLabels = (): string[] => {
  const calls = nav.replace.mock.calls;
  if (!calls.length) return [];
  const query = String(calls[calls.length - 1][0]).split('?')[1] ?? '';
  return new URLSearchParams(query).getAll('class_label');
};

describe('Spec verification - a class label containing a comma', () => {
  it('reaches the service whole and is written to the URL whole', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box(CLASS), [CLASS]);
    await waitFor(() => expect(asList(lastParams().class_label)).toEqual([CLASS]));
    await waitFor(() => expect(urlClassLabels()).toEqual([CLASS]));
  });

  it('with a plain label it reaches the service as two labels', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box(CLASS), [CLASS, 'ZZT Tap']);
    await waitFor(() => expect(asList(lastParams().class_label).sort()).toEqual([CLASS, 'ZZT Tap'].sort()));
  });

  it('a link carrying the comma label whole restores the control and the request', async () => {
    nav.params = new URLSearchParams();
    nav.params.append('class_label', CLASS);
    nav.params.append('class_label', 'ZZT Tap');
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => expect(asList(lastParams().class_label).sort()).toEqual([CLASS, 'ZZT Tap'].sort()));
    expect(selected(await box(CLASS))).toEqual([CLASS, 'ZZT Tap'].sort());
  });

  it('an older single-value link still reads back', async () => {
    nav.params = new URLSearchParams('class_label=ZZT+Basin');
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => expect(asList(lastParams().class_label)).toEqual(['ZZT Basin']));
    expect(selected(await box('ZZT Basin'))).toEqual(['ZZT Basin']);
  });
});

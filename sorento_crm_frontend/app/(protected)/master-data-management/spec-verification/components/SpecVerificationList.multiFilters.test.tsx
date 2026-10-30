/**
 * FILTER-MULTISELECT PR4: the Spec verification worklist's State and Class filters take several values
 * (OR within a filter, AND across), comma-joined to the service and in the page URL. An older link
 * holding one value reads back as a one-value filter.
 */
import React from 'react';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
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
  classes: ['ZZT Sink', 'ZZT Tap', 'ZZT Basin'],
};

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => {
  const calls = getSpecVerificationWorklist.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};
const lastUrlParam = (key: string): string[] => {
  const calls = nav.replace.mock.calls;
  if (!calls.length) return [];
  const target = String(calls[calls.length - 1][0]);
  // Class labels are free text and ride the URL as repeated params, so every value of the key counts.
  return setOf(new URLSearchParams(target.split('?')[1] ?? '').getAll(key).join(','));
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

describe('Spec verification - multi State and Class filters', () => {
  it('State and Class are multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('verified')).hasAttribute('multiple')).toBe(true);
    expect((await box('ZZT Tap')).hasAttribute('multiple')).toBe(true);
  });

  it('two states reach the service and the URL as a set of two; the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('verified'), ['verified', 'needs_reverify']);
    await waitFor(() => expect(setOf(lastParams().state)).toEqual(['needs_reverify', 'verified']));
    await waitFor(() => expect(lastUrlParam('state')).toEqual(['needs_reverify', 'verified']));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two classes and two states AND across', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('verified'), ['verified', 'unverified']);
    await user.selectOptions(await box('ZZT Tap'), ['ZZT Sink', 'ZZT Tap']);
    await waitFor(() => {
      expect(setOf(lastParams().state)).toEqual(['unverified', 'verified']);
      expect(setOf(lastParams().class_label)).toEqual(['ZZT Sink', 'ZZT Tap']);
    });
    await waitFor(() => expect(lastUrlParam('class_label')).toEqual(['ZZT Sink', 'ZZT Tap']));
  });

  it('Clear filters drops both multi filters', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('verified'), ['verified', 'unverified']);
    await waitFor(() => expect(setOf(lastParams().state)).toEqual(['unverified', 'verified']));
    const before = getSpecVerificationWorklist.mock.calls.length;
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    // Clearing returns to the cached unfiltered query (staleTime: Infinity), so a refetch is
    // optional; any request made after clearing carries no state, and the URL drops it.
    await waitFor(() => expect(lastUrlParam('state')).toEqual([]));
    for (const call of getSpecVerificationWorklist.mock.calls.slice(before)) {
      expect(setOf((call[0] as Record<string, unknown>).state)).toEqual([]);
    }
  });

  it('a link with several states and classes restores both controls and the request', async () => {
    nav.params = new URLSearchParams('state=verified%2Cneeds_reverify&class_label=ZZT+Sink&class_label=ZZT+Tap');
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(setOf(lastParams().state)).toEqual(['needs_reverify', 'verified']);
      expect(setOf(lastParams().class_label)).toEqual(['ZZT Sink', 'ZZT Tap']);
    });
    expect(selected(await box('verified'))).toEqual(['needs_reverify', 'verified']);
    expect(selected(await box('ZZT Tap'))).toEqual(['ZZT Sink', 'ZZT Tap']);
  });

  it('an older link with one state and one class reads back as one-value filters', async () => {
    nav.params = new URLSearchParams('state=unverified&class_label=ZZT+Basin');
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(setOf(lastParams().state)).toEqual(['unverified']);
      expect(setOf(lastParams().class_label)).toEqual(['ZZT Basin']);
    });
    expect(selected(await box('verified'))).toEqual(['unverified']);
  });
});

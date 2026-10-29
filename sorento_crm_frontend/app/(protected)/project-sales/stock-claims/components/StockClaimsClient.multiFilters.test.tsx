/**
 * FILTER-MULTISELECT PR6: the Stock claims Outcome filter takes several values (OR); one set reaches the service, clearing clears, no
 * 'all' value is ever sent.
 */
/**
 * P9 - the stock claims list (AC-H4), audit history since Stage 1C.
 *
 * A Borrow is now written already released, inside the confirmation of a sales order in
 * Fulfilment Planning, by the CS actor who confirms it. So this screen records what moved
 * and who moved it, and offers no answer to give: the accept and refuse routes behind those
 * buttons are gone. The two directions stay different facts and the screen keeps them
 * apart, because "nobody borrowed from us" is not "we borrowed from nobody".
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AllocationClaimRow } from '../../_shared/types/projectAllocation.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/stock-claims',
  useSearchParams: () => new URLSearchParams((globalThis as unknown as { __zztSearch?: string }).__zztSearch ?? ''),
}));

// Without this the shared DataGrid sits in its column-preferences fetch forever and renders
// skeleton rows instead of data.
const listingKeys: (string | null | undefined)[] = [];
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: vi.fn(), isLoading: false };
  },
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

const listAllocationClaims = vi.fn();

vi.mock('../../_shared/services/projectAllocationService', () => ({
  listSalesOrderAllocations: vi.fn(),
  listAllocationCandidates: vi.fn(),
  listAllocationClaims: (...args: unknown[]) => listAllocationClaims(...args),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

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

import { StockClaimsClient } from './StockClaimsClient';

function envelope(rows: AllocationClaimRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClaims() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StockClaimsClient />
    </QueryClientProvider>,
  );
}

/** Radix opens its menus on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /^filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  listAllocationClaims.mockResolvedValue(envelope([]));
});


const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : [String(v ?? '')]).flatMap((s) => s.split(',')).map((s) => s.trim()).filter(Boolean).sort();
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

const last = () => {
  const args = listAllocationClaims.mock.calls.at(-1) as unknown[];
  return args.find((a) => a && typeof a === 'object') as Record<string, unknown>;
};
const FILTERS: [string, string, string][] = [['state', 'accepted', 'refused']];

describe('stock-claims/components/StockClaimsClient.multiFilters.test.tsx - multi filters', () => {
  beforeEach(() => {
    (globalThis as unknown as { __zztSearch?: string }).__zztSearch = '';
    Element.prototype.scrollIntoView = vi.fn();
  });

  it.each(FILTERS)('%s is a multi control', async (_p, a) => {
    renderClaims();
    await waitFor(() => expect(listAllocationClaims).toHaveBeenCalled());
    openFilters();
    expect((await box(a)).hasAttribute('multiple')).toBe(true);
  });

  it.each(FILTERS)('%s: two values reach the service as one set', async (param, a, b) => {
    const user = userEvent.setup();
    renderClaims();
    await waitFor(() => expect(listAllocationClaims).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(last()[param])).toEqual([a, b].sort()));
  });

  it.each(FILTERS)('%s: clearing sends nothing, never an all value', async (param, a, b) => {
    const user = userEvent.setup();
    renderClaims();
    await waitFor(() => expect(listAllocationClaims).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(last()[param])).toEqual([a, b].sort()));
    await user.keyboard('{Escape}');
    openFilters();
    await user.deselectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(last()[param])).toEqual([]));
    for (const [params] of listAllocationClaims.mock.calls) {
      expect(setOf((params as Record<string, unknown>)[param])).not.toContain('all');
    }
  });
});

/**
 * FILTER-MULTISELECT PR6: the Plans page State filter takes several values (OR); one comma-joined set reaches
 * the service. State stays required: unticking the last state keeps one, so the page never asks for none.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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
  usePathname: () => '/project-sales/plans',
  useSearchParams: () => new URLSearchParams(''),
}));

// Without this the shared DataGrid sits in its column-preferences fetch forever and
// renders skeleton rows instead of data.
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

const listPlans = vi.fn();

vi.mock('../../_shared/services/plansService', () => ({
  listPlans: (...args: unknown[]) => listPlans(...args),
}));

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

import { PlansClient } from './PlansClient';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => listPlans.mock.calls.at(-1)?.[0] as Record<string, unknown>;
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
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), { button: 0, ctrlKey: false });
}
function renderClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlansClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listPlans.mockResolvedValue({ data: [], total: 0, page: 1, limit: 25 });
});

describe('Plans - multi State filter', () => {
  it('opens on active only', async () => {
    renderClient();
    await waitFor(() => expect(listPlans).toHaveBeenCalled());
    expect(setOf(lastParams().state)).toEqual(['active']);
  });

  it('State is a multi control', async () => {
    renderClient();
    await waitFor(() => expect(listPlans).toHaveBeenCalled());
    openFilters();
    expect((await box('superseded')).hasAttribute('multiple')).toBe(true);
  });

  it('two states reach the service as one set', async () => {
    const user = userEvent.setup();
    renderClient();
    await waitFor(() => expect(listPlans).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box('superseded'), ['active', 'challenged']);
    await waitFor(() => expect(setOf(lastParams().state)).toEqual(['active', 'challenged']));
  });

  it('unticking every state keeps one: State is required, the service is never asked for none', async () => {
    const user = userEvent.setup();
    renderClient();
    await waitFor(() => expect(listPlans).toHaveBeenCalled());
    openFilters();
    await user.deselectOptions(await box('superseded'), ['active']);
    await waitFor(() => expect(listPlans.mock.calls.length).toBeGreaterThan(0));
    for (const [params] of listPlans.mock.calls) {
      expect(setOf((params as Record<string, unknown>).state).length).toBeGreaterThan(0);
    }
  });
});

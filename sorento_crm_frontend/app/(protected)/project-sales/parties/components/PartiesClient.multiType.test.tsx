/**
 * FILTER-MULTISELECT PR6: the Parties list's Type filter takes several values (OR); the param rides comma-joined,
 * clearing clears, the sentinel never ships.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/parties',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));
const useProjectParties = vi.hoisted(() => vi.fn());
vi.mock('../../_shared/hooks/useProjects', () => ({
  useProjectParties: (...args: unknown[]) => useProjectParties(...args),
  usePartyMutations: () => ({ remove: { mutate: vi.fn(), isPending: false }, create: { mutate: vi.fn() }, update: { mutate: vi.fn() } }),
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


import { PartiesClient } from './PartiesClient';

const ROW = {
  id: 'p1', party_type: 'architect', name: 'ZZT Veritas Architects', is_active: true, project_count: 2,
  created_at: '2026-08-01T02:00:00',
};
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => useProjectParties.mock.calls[useProjectParties.mock.calls.length - 1][0] as Record<string, unknown>;
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

async function render_() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PartiesClient />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT Veritas Architects');
  openFilters();
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  useProjectParties.mockReturnValue({
    data: { data: [ROW], pagination: { total: 1, page: 1, limit: 200 } }, isLoading: false, isFetching: false, error: null,
  });
});
afterEach(() => cleanup());

describe('Parties - multi Type filter', () => {
  it('starts with no type', async () => {
    await render_();
    expect(setOf(lastParams().party_type)).toEqual([]);
  });

  it('Type is a multi control', async () => {
    await render_();
    expect((await box('architect')).hasAttribute('multiple')).toBe(true);
  });

  it('two types reach the hook as a set of two', async () => {
    const user = userEvent.setup();
    await render_();
    await user.selectOptions(await box('architect'), ['architect', 'developer']);
    await waitFor(() => expect(setOf(lastParams().party_type)).toEqual(['architect', 'developer']));
  });

  it('unticking every type sends no party_type, never an "all" value', async () => {
    const user = userEvent.setup();
    await render_();
    await user.selectOptions(await box('architect'), ['architect']);
    await waitFor(() => expect(setOf(lastParams().party_type)).toEqual(['architect']));
    await user.deselectOptions(await box('architect'), ['architect']);
    await waitFor(() => expect(setOf(lastParams().party_type)).toEqual([]));
    for (const [params] of useProjectParties.mock.calls) {
      expect(setOf((params as Record<string, unknown>).party_type)).not.toContain('all');
    }
  });
});

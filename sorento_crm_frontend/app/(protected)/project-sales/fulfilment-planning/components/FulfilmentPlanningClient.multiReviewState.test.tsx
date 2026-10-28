/**
 * FILTER-MULTISELECT PR6: the Fulfilment planning Review state filter takes several values (OR),
 * comma-joined to the list service; nothing chosen sends nothing (the "Any" sentinel is never sent).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
  usePathname: () => '/project-sales/fulfilment-planning',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
const listFulfilmentPlanning = vi.hoisted(() => vi.fn());
vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  listFulfilmentPlanning: (...args: unknown[]) => listFulfilmentPlanning(...args),
  getReconciliation: vi.fn(), rerunReconciliation: vi.fn(), adoptSalesOrder: vi.fn(), getSupply: vi.fn(), getPlanningBoard: vi.fn(),
  confirmSupply: vi.fn(), confirmMany: vi.fn(), putLineDraft: vi.fn(), deleteLineDraft: vi.fn(), ConfirmSupplyError: class extends Error {},
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'user-1', name: 'Test Planner' } }, status: 'authenticated' }),
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

import { FulfilmentPlanningClient } from './FulfilmentPlanningClient';

const ROW = {
  id: 'pso-1', provisional_ref: 'PSO-000123', autocount_doc_no: 'SO376201', project_id: 'proj-1', project_code: 'PRJ-0041',
  project_name: 'ZZT Tuju Residences', customer_name: 'Buimaco Sdn Bhd (Project)', po_number: 'HQ/26/01/121', area_group: 'TOWER',
  status: 'published', line_count: 4, lines_linked: 4, exception_count: 0, review_state: 'needs_cs_review', updated_at: '2026-08-14T02:41:00',
};
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => listFulfilmentPlanning.mock.calls[listFulfilmentPlanning.mock.calls.length - 1][0] as Record<string, unknown>;
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
      <FulfilmentPlanningClient />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT Tuju Residences');
  openFilters();
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  listFulfilmentPlanning.mockResolvedValue({ data: [ROW], total: 1, page: 1, limit: 25 });
});
afterEach(() => cleanup());

describe('Fulfilment planning - multi Review state filter', () => {
  it('Review state is a multi control', async () => {
    await render_();
    expect((await box('not_started')).hasAttribute('multiple')).toBe(true);
  });

  it('two review states reach the service as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await render_();
    await user.selectOptions(await box('not_started'), ['not_started', 'confirmed']);
    await waitFor(() => expect(setOf(lastParams().review_state)).toEqual(['confirmed', 'not_started']));
    // The Filters menu is modal, so its button is hidden from the a11y tree while it is open.
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(screen.getByRole('button', { name: /^filters/i })).getByText('1')).toBeInTheDocument());
  });

  it('the Any sentinel is never sent', async () => {
    await render_();
    await box('not_started');
    expect(setOf(lastParams().review_state)).toEqual([]);
  });

  it('unticking every state drops the filter', async () => {
    const user = userEvent.setup();
    await render_();
    await user.selectOptions(await box('not_started'), ['not_started', 'confirmed']);
    await waitFor(() => expect(setOf(lastParams().review_state)).toEqual(['confirmed', 'not_started']));
    await user.deselectOptions(await box('not_started'), ['not_started', 'confirmed']);
    await waitFor(() => expect(setOf(lastParams().review_state)).toEqual([]));
  });
});

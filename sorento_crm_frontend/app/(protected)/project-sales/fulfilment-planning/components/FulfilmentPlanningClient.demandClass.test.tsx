/**
 * DEALER-PLANNING PR 2, R6: the Fulfilment planning list takes a multi-select Class filter that
 * defaults to Project (so the screen shows today's list), and each row states its class. Retail
 * and other orders are reached by adding Retail. Written test-first: the control, the default
 * and the row cell do not exist yet.
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
  demand_class: 'retail',
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

async function render_(open = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FulfilmentPlanningClient />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT Tuju Residences');
  if (open) openFilters();
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  listFulfilmentPlanning.mockResolvedValue({ data: [ROW], total: 1, page: 1, limit: 25 });
});
afterEach(() => cleanup());

describe('Fulfilment planning - Class filter (R6)', () => {
  it('opens on Project alone, so the first call returns what the screen returns today', async () => {
    await render_(false);
    expect(setOf(lastParams().demand_class)).toEqual(['project']);
  });

  it('offers Project and Retail in one multi control', async () => {
    await render_();
    const control = await box('retail');
    expect(control.hasAttribute('multiple')).toBe(true);
    expect(control.querySelector('option[value="project"]')).not.toBeNull();
  });

  it('Project plus Retail reach the service as a set of two', async () => {
    const user = userEvent.setup();
    await render_();
    await user.selectOptions(await box('retail'), ['project', 'retail']);
    await waitFor(() => expect(setOf(lastParams().demand_class)).toEqual(['project', 'retail']));
  });

  it('a row states its class', async () => {
    await render_(false);
    expect(await screen.findByText(/^Retail$/)).toBeInTheDocument();
  });
});

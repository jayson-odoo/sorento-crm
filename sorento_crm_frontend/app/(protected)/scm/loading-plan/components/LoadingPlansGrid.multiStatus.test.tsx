/**
 * FILTER-MULTISELECT PR5: the Loading plans list's Status filter takes several statuses (OR within the
 * filter) and "Active (planning and sent)" stays a pseudo-value that ORs with real statuses. One chip
 * names the chosen values. Harness mirrors LoadingPlansGrid.test.tsx (service mocked, real hook).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(), cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/loading-plan',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('./PlanContainerDialog', () => ({ PlanContainerDialog: () => null }));
const getLoadingPlanList = vi.hoisted(() => vi.fn());
vi.mock('../../services/fulfilmentService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/fulfilmentService')>();
  return { ...actual, getLoadingPlanList: (...a: unknown[]) => getLoadingPlanList(...a), deleteLoadingPlan: vi.fn() };
});
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

import { LoadingPlansGrid } from './LoadingPlansGrid';

const PLAN = {
  id: 'plan-1', supplier_id: 'sup-1', supplier_name: 'ZZT PLAN SUPPLIER', supplier_email: 'zzt@example.test',
  started_at: '2026-08-27T14:02:00', plan_horizon_date: '2026-09-30', document_kind: 'stock_list', document_label: 'Stock list',
  source_attachment_id: null, source_attachment_filename: null, status: 'planning', sent_channel: null, sent_at: null,
  opened_at: null, last_opened_at: null, open_count: 0, cancelled_at: null, cancelled_by: null, line_edits: {},
  to_request_qty: 10, to_request_cbm: 1,
};
const lastParams = () => getLoadingPlanList.mock.calls[getLoadingPlanList.mock.calls.length - 1][0] as Record<string, unknown>;
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
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
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <LoadingPlansGrid />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT PLAN SUPPLIER');
  await user.click(filtersButton());
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  getLoadingPlanList.mockResolvedValue({ data: [PLAN], total: 1 });
});
afterEach(() => cleanup());

describe('Loading plans - multi Status filter', () => {
  it('Status is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('cancelled')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses reach the service as a set of two, with one chip naming both', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('cancelled'), ['planning', 'cancelled']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['cancelled', 'planning']));
    await waitFor(() => expect(screen.getByText('Status: Planning, Cancelled')).toBeInTheDocument());
  });

  it('the Active group stays a pseudo-value that combines with a real status', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('cancelled'), ['active', 'cancelled']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['active', 'cancelled']));
  });

  it('unticking every status goes back to the default view (the Active group or no filter)', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('cancelled'), ['planning', 'cancelled']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['cancelled', 'planning']));
    await user.deselectOptions(await box('cancelled'), ['planning', 'cancelled']);
    await waitFor(() => {
      const v = setOf(lastParams().status);
      expect(v.length === 0 || (v.length === 1 && v[0] === 'active')).toBe(true);
    });
  });
});

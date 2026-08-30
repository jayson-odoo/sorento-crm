/**
 * ReorderPolicyGrid - loading / error / data / empty-hint states.
 *   AC-STD-4 (every state renders), AC-LIST-1 (readable scope labels, no UUID),
 *   AC-LIST-4 (global-only empty hint), AC-LIST-5 ("next reorder run" copy),
 *   AC-DEL-2 (global row has no delete affordance).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
/* The grace window is the server's; what this file proves is that the row parks one. */
const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'reorder_policy.delete',
  entity_type: 'reorder_policy',
  entity_id: 'p-1',
  commit_at: '2026-08-30T10:00:10',
  window_seconds: 10,
});
vi.mock('sonner', () => ({
  // `dismiss` is load-bearing: the countdown's toast is dismissed when the row
  // unmounts, and a stub without it throws out of an effect no assertion catches.
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// jsdom polyfills for ScrollArea / DataGrid.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/policies',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// DataGrid persists column prefs via this hook (fires network) - stub it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const hooks = vi.hoisted(() => ({
  useReorderPolicies: vi.fn(),
  useCreatePolicy: vi.fn(),
  useUpdatePolicy: vi.fn(),
  useDeletePolicy: vi.fn(),
  useProductScopeOptions: vi.fn(),
  useClassScopeOptions: vi.fn(),
}));
vi.mock('../hooks/usePolicies', () => hooks);

import { ReorderPolicyGrid } from './ReorderPolicyGrid';
import type { ReorderPolicyRow } from '../types/policy.types';

function row(over: Partial<ReorderPolicyRow>): ReorderPolicyRow {
  return {
    id: 'pol-x',
    scope_type: 'global',
    scope_ref: null,
    scope_label: '-',
    policy_type: 'reorder_point',
    service_level: null,
    safety_stock_method: 'fixed_days',
    safety_days: 7,
    review_period_days: null,
    forecast_window_days: 90,
    baseline_source: null,
    spike_handling: null,
    buy_scope: null,
    dead_stock_days: 180,
    overstock_days: 120,
    min_override: null,
    max_override: null,
    priority: 0,
    is_active: true,
    supplier_selection: 'best_score',
    lead_time_default_days: 14,
    ...over,
  };
}

const GLOBAL = row({ id: 'pol-global', scope_type: 'global', scope_label: '-', priority: 0 });
const CLASS = row({
  id: 'pol-class',
  scope_type: 'product_class',
  scope_ref: 'BRK',
  scope_label: 'Braking',
  priority: 10,
});

function mockList(over: Partial<ReturnType<typeof hooks.useReorderPolicies>>) {
  hooks.useReorderPolicies.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...over,
  });
}

function renderGrid() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReorderPolicyGrid />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(hooks).forEach((f) => f.mockReset());
  hooks.useCreatePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useUpdatePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useDeletePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useProductScopeOptions.mockReturnValue({ data: [], isLoading: false });
  hooks.useClassScopeOptions.mockReturnValue({ data: [], isLoading: false });
});

describe('ReorderPolicyGrid', () => {
  it('shows the "next reorder run" precedence note (AC-LIST-5)', () => {
    mockList({ data: { data: [GLOBAL, CLASS], total: 2 } });
    renderGrid();
    expect(screen.getByText(/Changes take effect on the next/i)).toBeInTheDocument();
    expect(screen.getByText(/most-specific-first/i)).toBeInTheDocument();
  });

  it('drives the list hook with server-side paging/sort/search args (AC-LIST-3)', () => {
    mockList({ data: { data: [GLOBAL, CLASS], total: 2 } });
    renderGrid();
    // Server-side: pagination + sorting + (debounced) search are threaded into
    // the query so nothing is truncated and search reaches backend-only fields.
    expect(hooks.useReorderPolicies).toHaveBeenCalledWith(
      expect.objectContaining({ pageIndex: 0, pageSize: 10, sorting: [], searchQuery: '' }),
    );
  });

  it('renders the error state when the list fails', () => {
    mockList({ isError: true, error: new Error('Failed to load reorder policies.') });
    renderGrid();
    expect(screen.getByText('Failed to load reorder policies.')).toBeInTheDocument();
  });

  it('renders a loading grid without any data rows', () => {
    mockList({ isLoading: true });
    renderGrid();
    // No policy scope target text while loading.
    expect(screen.queryByText('Braking')).not.toBeInTheDocument();
    // Toolbar affordance still present.
    expect(screen.getByRole('button', { name: /Add policy/i })).toBeInTheDocument();
  });

  it('renders data rows with readable scope labels (no UUID; AC-LIST-1/NAV-4)', () => {
    mockList({ data: { data: [GLOBAL, CLASS], total: 2 } });
    renderGrid();
    expect(screen.getByText('Braking')).toBeInTheDocument();
    // Scope badges use friendly wording.
    expect(screen.getByText('Product class')).toBeInTheDocument();
    expect(screen.getAllByText('Global default').length).toBeGreaterThan(0);
  });

  it('renders the global-only empty hint (AC-LIST-4)', () => {
    mockList({ data: { data: [GLOBAL], total: 1 } });
    renderGrid();
    expect(
      screen.getByText(/Only the global default policy is configured/i),
    ).toBeInTheDocument();
  });

  it('does NOT render the empty hint once a non-global override exists', () => {
    mockList({ data: { data: [GLOBAL, CLASS], total: 2 } });
    renderGrid();
    expect(screen.queryByText(/Only the global default policy is configured/i)).not.toBeInTheDocument();
  });

  it('global row has no delete affordance; overrides do (AC-DEL-2)', () => {
    mockList({ data: { data: [GLOBAL, CLASS], total: 2 } });
    renderGrid();
    // Exactly one delete button (the class override), not the global row.
    const deletes = screen.getAllByRole('button', { name: /Delete policy/i });
    expect(deletes).toHaveLength(1);
    // Both rows are editable.
    expect(screen.getAllByRole('button', { name: /Edit policy/i })).toHaveLength(2);
  });

  it('parks the delete rather than opening a dialog (AC-DEL-1, S6-10)', async () => {
    const { fireEvent, waitFor } = await import('@testing-library/react');
    mockList({ data: { data: [GLOBAL, CLASS], total: 2 } });
    renderGrid();
    fireEvent.click(screen.getByRole('button', { name: /Delete policy/i }));

    // D7: the press IS the action, and Cancel in the countdown is the way back.
    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'reorder_policy.delete',
          entityType: 'reorder_policy',
        }),
      ),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

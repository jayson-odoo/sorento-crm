/**
 * `KindsTab` — S7b Phase 2c gate.
 *
 * Group 1 item 1 (AC-P17): the "no rules" / "no terms" affordance must be
 * driven by the server-computed booleans `has_no_rules` / `has_no_terms`, NOT
 * by `rule_count === 0` / `term_count === 0`. Fixtures below are deliberately
 * CONTRADICTORY (a flagged row with a non-zero count, and an unflagged row
 * with a zero count) so a count-driven implementation would visibly disagree
 * with a boolean-driven one.
 *
 * Group 1 item 2 (AC-P12): deleting a Kind still referenced by a Term or Rule
 * is refused, and the refusal names BOTH counts.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const hooks = vi.hoisted(() => ({
  useKinds: vi.fn(),
  useCreateKind: vi.fn(),
  useUpdateKind: vi.fn(),
  useDeleteKind: vi.fn(),
}));
vi.mock('../hooks/useWarrantyConfig', () => hooks);

import { KindsTab } from './KindsTab';
import type { WarrantyKindRow } from '../types/warranty-config.types';

function kind(over: Partial<WarrantyKindRow>): WarrantyKindRow {
  return {
    id: 'kind-1',
    code: 'water_closet',
    name: 'Water Closet',
    consumer_label: null,
    consumer_icon: null,
    sort_order: 1,
    is_active: true,
    rule_count: 0,
    term_count: 0,
    has_no_rules: false,
    has_no_terms: false,
    ...over,
  };
}

// A "flagged but non-zero" row: the boolean says unreachable/uncovered, but
// the counts (deliberately) disagree. Only a boolean-driven implementation
// gets this right.
const FLAGGED_WITH_COUNTS = kind({
  id: 'kind-flagged',
  name: 'Mirror Cabinet',
  rule_count: 37,
  term_count: 79,
  has_no_rules: true,
  has_no_terms: false,
});

// The mirror-image row: rule_count is zero, but the boolean says it IS
// reachable. term_count is deliberately non-zero and distinct from every
// other number in this file, so text queries can never collide.
const ZERO_BUT_UNFLAGGED = kind({
  id: 'kind-unflagged',
  name: 'Bathroom Furniture',
  rule_count: 0,
  term_count: 41,
  has_no_rules: false,
  has_no_terms: false,
});

const deleteMutate = vi.fn().mockResolvedValue(undefined);

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <KindsTab />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(hooks).forEach((f) => f.mockReset());
  deleteMutate.mockClear();
  hooks.useCreateKind.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useUpdateKind.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useDeleteKind.mockReturnValue({ mutateAsync: deleteMutate, isPending: false });
});

describe('KindsTab — AC-P17: the zero/non-zero flag is the server boolean, not the count', () => {
  it('a row with has_no_rules=true, rule_count=37 (contradictory) is FLAGGED on Rules', () => {
    hooks.useKinds.mockReturnValue({
      data: [FLAGGED_WITH_COUNTS],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    renderTab();

    const rulesValue = screen.getByText('37');
    // The flagged cell renders as a destructive Badge, not a plain span.
    const badge = rulesValue.closest('[data-slot="badge"]');
    expect(badge).not.toBeNull();
    expect(badge?.className ?? '').toMatch(/destructive/);
  });

  it('the SAME row is NOT flagged on Terms (has_no_terms=false, even though rule_count math would tempt a count-based check)', () => {
    hooks.useKinds.mockReturnValue({
      data: [FLAGGED_WITH_COUNTS],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    renderTab();

    const termsValue = screen.getByText('79');
    expect(termsValue.getAttribute('data-slot')).not.toBe('badge');
    expect(termsValue.closest('[data-slot="badge"]')).toBeNull();
    expect(termsValue.className).toContain('tabular-nums');
  });

  it('a row with rule_count=0 but has_no_rules=false is NOT flagged (a count-driven check would wrongly flag it)', () => {
    hooks.useKinds.mockReturnValue({
      data: [ZERO_BUT_UNFLAGGED],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    renderTab();

    const rulesValue = screen.getByText('0');
    expect(rulesValue.closest('[data-slot="badge"]')).toBeNull();
    expect(rulesValue.className).toContain('tabular-nums');
  });

  it('the top summary count ("N of M have no rule") counts has_no_rules, not rule_count === 0', () => {
    hooks.useKinds.mockReturnValue({
      data: [FLAGGED_WITH_COUNTS, ZERO_BUT_UNFLAGGED],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    renderTab();

    // Exactly one of the two rows has has_no_rules=true, even though the
    // OTHER row has rule_count literally 0.
    expect(screen.getByText(/1 of 2 have no rule/i)).toBeInTheDocument();
  });
});

describe('KindsTab — AC-P12: deleting a referenced Kind is refused, naming BOTH counts', () => {
  it('a Kind with terms and rules cannot be deleted, and the refusal names both counts', async () => {
    const referenced = kind({
      id: 'kind-ref',
      name: 'Water Closet',
      term_count: 3,
      rule_count: 2,
      has_no_terms: false,
      has_no_rules: false,
    });
    hooks.useKinds.mockReturnValue({
      data: [referenced],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    renderTab();

    fireEvent.click(screen.getByRole('button', { name: /Delete kind/i }));

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('Cannot delete')).toBeInTheDocument();
    expect(within(dialog).getByText('3')).toBeInTheDocument();
    expect(within(dialog).getByText('2')).toBeInTheDocument();
    expect(within(dialog).getByText(/terms/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/rules/i)).toBeInTheDocument();
    // The refusal dialog never offers a destructive confirm — only "Close".
    expect(within(dialog).queryByRole('button', { name: /^Delete$/i })).not.toBeInTheDocument();
  });

  it('an unreferenced Kind (has_no_terms AND has_no_rules) goes straight to the hard-delete confirmation', async () => {
    const clean = kind({
      id: 'kind-clean',
      name: 'Unused Kind',
      term_count: 0,
      rule_count: 0,
      has_no_terms: true,
      has_no_rules: true,
    });
    hooks.useKinds.mockReturnValue({
      data: [clean],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    renderTab();

    fireEvent.click(screen.getByRole('button', { name: /Delete kind/i }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Confirm delete')).toBeInTheDocument();
    expect(within(dialog).getByText(/This action cannot be undone/i)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: /^Delete$/i }));
    await vi.waitFor(() => expect(deleteMutate).toHaveBeenCalledWith('kind-clean'));
  });
});

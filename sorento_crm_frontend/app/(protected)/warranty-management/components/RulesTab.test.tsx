/**
 * `RulesTab` - S7b Phase 2c gate, Group 2 item 9 (grid half of AC-P24).
 *
 * "Strict at write, tolerant at read": an unknown `match_type` never reaches
 * the grid as a blank/`undefined` badge. The `match_type` column goes through
 * `formatMatchTypeLabel`, which falls back to the RAW stored value, so a row
 * written before the frontend knew about that match type is still readable
 * instead of rendering an empty badge that looks like a rendering bug.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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
  useKindOptions: vi.fn(),
  useKindRules: vi.fn(),
  useCreateKindRule: vi.fn(),
  useUpdateKindRule: vi.fn(),
  useDeleteKindRule: vi.fn(),
  useTestKindRules: vi.fn(),
}));
vi.mock('../hooks/useWarrantyConfig', () => hooks);

import { RulesTab } from './RulesTab';
import type { WarrantyKindRuleRow } from '../types/warranty-config.types';

const ROW: WarrantyKindRuleRow = {
  id: 'rule-9',
  kind_id: 'kind-mirror',
  kind_code: 'mirror_cabinet',
  kind_name: 'Mirror Cabinet',
  // @ts-expect-error - deliberately a match_type the FE label map does not know.
  match_type: 'something_new',
  match_value: 'ABC',
  priority: 0,
};

beforeEach(() => {
  Object.values(hooks).forEach((f) => f.mockReset());
  hooks.useKindOptions.mockReturnValue({ data: [{ id: 'kind-mirror', code: 'mirror_cabinet', name: 'Mirror Cabinet' }] });
  hooks.useKindRules.mockReturnValue({
    data: [ROW],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
  });
  hooks.useCreateKindRule.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useUpdateKindRule.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useDeleteKindRule.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useTestKindRules.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RulesTab />
    </QueryClientProvider>,
  );
}

describe('RulesTab grid - AC-P24 tolerant read: an unknown match_type renders readable, not blank', () => {
  it('renders a non-empty match-type badge for a row whose match_type the FE label map does not know', () => {
    renderTab();

    // The value column ("ABC") always renders, so locate the row via it, then
    // check the SAME row's match-type badge cell is not left empty.
    const valueCell = screen.getByText('ABC');
    const row = valueCell.closest('tr');
    expect(row).not.toBeNull();
    // "Mirror Cabinet" + "ABC" + "0" (priority) all render regardless; the
    // match-type badge is the one cell this AC is actually about, so pin its
    // text directly rather than trusting an absence-of-"undefined" check
    // (JSX renders `undefined` as nothing, so that check would pass vacuously).
    expect(row?.textContent ?? '').toContain('something_new');
  });
});

/**
 * SPEC-ICON-COMBINED FU F3: a numeric key carries icons (PRICETAG-UPGRADE-VARIANTS S4), so it
 * shows Icon order in view and edit. Enum and boolean are unchanged.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HeaderTab } from './HeaderTab';
import { projectSpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

function row(over: Partial<SpecRegistryKey>): SpecRegistryKey {
  return {
    spec_key: 'trap_length', label: 'Trap outlet length', data_type: 'numeric', unit: 'mm',
    allowed_values: [], synonyms: {}, excluded_values: [], user_values: [], suppressed_values: [],
    value_weights: {}, derivation_rules: [], effective_rules: [], applies_when: {}, read_from: 'rules',
    rank_weight: 1, measured_coverage: null, source: 'seed', user_synonyms: {}, suppressed_synonyms: {},
    match_tolerance: 0, match_decay: 0, is_active: true, icon_order: 3, ...over,
  } as unknown as SpecRegistryKey;
}
const wrap = (node: React.ReactNode) => (
  <QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>
);

describe('FU F3 HeaderTab Icon order by data type', () => {
  it('a numeric key shows Icon order in view', () => {
    render(wrap(<HeaderTab row={row({})} mode="view" draft={null} setDraft={() => {}} />));
    expect(screen.getByText('Icon order')).toBeInTheDocument();
    expect(screen.getByTestId('icon-order-value')).toHaveTextContent('3');
  });

  it('a numeric key offers the Icon order input in edit', () => {
    const r = row({});
    render(wrap(<HeaderTab row={r} mode="edit" draft={projectSpecKeyDraft(r)} setDraft={() => {}} />));
    expect(screen.getByLabelText('Icon order')).toHaveValue(3);
  });

  it('enum and boolean still show it, free text still does not', () => {
    const cases: [Partial<SpecRegistryKey>, boolean][] = [
      [{ data_type: 'enum', allowed_values: ['a'] }, true],
      [{ data_type: 'boolean', allowed_values: [] }, true],
      [{ data_type: 'text', allowed_values: [] }, false],
    ];
    for (const [over, shown] of cases) {
      const { unmount } = render(wrap(<HeaderTab row={row(over)} mode="view" draft={null} setDraft={() => {}} />));
      expect(screen.queryByText('Icon order') !== null).toBe(shown);
      unmount();
    }
  });
});

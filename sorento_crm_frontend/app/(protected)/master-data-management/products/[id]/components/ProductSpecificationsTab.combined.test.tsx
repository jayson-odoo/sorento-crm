/**
 * SPEC-ICON-COMBINED F3: on the Specifications tab a conditioned icon shows on its HOST row only,
 * and only when every partner row is held, with a muted visible hint naming the partners
 * ("shown because Trap = S trap"). The partner row itself shows nothing extra.
 *
 * Uses the REAL `useSpecValueIcons` (permissions and the feature-icons service mocked) and the
 * REAL tab; `SpecTable` is a stub that calls the tab's adornment for every row it is handed.
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ProductSpecificationsTab from './ProductSpecificationsTab';
import { resetKitLibraryCache } from '@/lib/dealer-kit/kit-library-cache';
import { useSpecValueIcons } from '../../hooks/useSpecValueIcons';
import { renderHook } from '@testing-library/react';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));
vi.mock('@/components/spec-table', () => ({
  SpecTable: ({
    rows,
    valueAdornment,
  }: {
    rows: { specKey: string }[];
    valueAdornment?: (row: unknown) => ReactNode;
  }) => (
    <div data-testid="spec-table-stub">
      {rows.map((r) => (
        <div key={r.specKey} data-row={r.specKey}>
          {valueAdornment?.(r)}
        </div>
      ))}
    </div>
  ),
  AddSpecificationDialog: () => null,
}));

const permissions = { set: new Set<string>(['dealer_kit.tag_templates.view']) };
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissionSet: permissions.set, isLoading: false }),
}));

const listFeatureIcons = vi.fn();
vi.mock('@/app/(protected)/dealer-kit/services/tagDataService', () => ({
  listFeatureIcons: () => listFeatureIcons(),
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn().mockResolvedValue({}),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

const useProductSpecTable = vi.fn();
vi.mock('../../hooks/useProductSpecTable', () => ({
  DETAIL_KEY: (productId: string) => ['product-spec-detail', productId],
  useProductSpecTable: (...a: unknown[]) => useProductSpecTable(...a),
}));
vi.mock('../../hooks/useProducts', () => ({
  useProduct: () => ({
    data: { id: 'p-1', product_code: 'SRTWC286-SH-150', product_name: 'WC', list_price: null, price_tag_description: null },
    isLoading: false,
  }),
  useUpdateProduct: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const ICONS = [
  { id: 's', name: 'S trap', spec_key: 'trap_type', values: ['s_trap'], url: 'https://cdn/s.png' },
  {
    id: 's150',
    name: 'S trap 150mm',
    spec_key: 'trap_length',
    values: ['150'],
    url: 'https://cdn/s150.png',
    conditions: [{ spec_key: 'trap_type', value: 's_trap' }],
  },
];

function specRow(specKey: string, label: string, value: string | number, valueLabels: Record<string, string> = {}) {
  return {
    specKey,
    label,
    value,
    unit: null,
    dataType: 'text',
    options: [],
    source: 'derived',
    evidence: null,
    unknownKey: false,
    valueLabels,
    conflict: null,
  };
}
const TRAP = specRow('trap_type', 'Trap', 's_trap', { s_trap: 'S trap' });
const LENGTH = specRow('trap_length', 'Trap length', 150);

function mountWith(rows: ReturnType<typeof specRow>[]) {
  useProductSpecTable.mockReturnValue({
    detail: {
      product_id: 'p-1', product_code: 'SRTWC286-SH-150', category_code: 'BR-WC', searchable: true,
      diagnosis: { reason: 'eligible', class_label: 'WC', brand_hint: 'Sorento', suffix: null },
      spec: { values: {}, provenance: {}, rendered_text: '', status: 'authored', derived_at: '2026-08-01T09:00:00' },
      exceptions: [], source_text: '',
      verification: { state: 'unverified', verified_by_name: null, verified_at: null, invalidated_at: null,
        invalidated_reason: null, invalidated_by_name: null, invalidated_diff: null },
      values_hash: 'h',
    },
    rows, registry: [], applicableKeys: [], otherKeys: [], heldKeys: [],
    isLoading: false, error: null, refetch: vi.fn(), verify: vi.fn(), verificationBusy: false,
    setValue: vi.fn(), tombstone: vi.fn(), revert: vi.fn(), addValue: vi.fn(), createKey: vi.fn(),
    checkSimilarKey: vi.fn(), createKeyAsync: vi.fn(), checkSimilarKeyAsync: vi.fn(),
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProductSpecificationsTab productId="p-1" />
    </QueryClientProvider>,
  );
}

const rowEl = (key: string) => document.querySelector(`[data-row="${key}"]`) as HTMLElement;

beforeEach(() => {
  resetKitLibraryCache();
  listFeatureIcons.mockReset().mockResolvedValue(ICONS);
});
afterEach(cleanup);

describe('F3 Specifications tab conditioned icon', () => {
  it('F3 host row shows the icon and the hint when the partner row is held', async () => {
    mountWith([TRAP, LENGTH]);
    await waitFor(() => expect(rowEl('trap_length').querySelector('[data-spec-icon="s150"]')).toBeTruthy());
    const hint = rowEl('trap_length').querySelector('[data-spec-icon-reason]');
    expect(hint).toBeTruthy();
    expect(hint?.textContent).toBe('shown because Trap = S trap');
  });

  it('F3 partner row shows its own single icon but no combined icon and no hint', async () => {
    mountWith([TRAP, LENGTH]);
    await waitFor(() => expect(rowEl('trap_type').querySelector('[data-spec-icon="s"]')).toBeTruthy());
    expect(rowEl('trap_type').querySelector('[data-spec-icon="s150"]')).toBeNull();
    expect(rowEl('trap_type').querySelector('[data-spec-icon-reason]')).toBeNull();
    // A plain icon carries no hint on its own host row either.
    expect(document.querySelectorAll('[data-spec-icon-reason]').length).toBe(1);
  });

  it('F3 host row shows nothing when the partner value is not held', async () => {
    mountWith([specRow('trap_type', 'Trap', 'p_trap', { p_trap: 'P trap' }), LENGTH]);
    await waitFor(() => expect(listFeatureIcons).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30));
    expect(rowEl('trap_length').querySelector('[data-spec-icon]')).toBeNull();
    expect(rowEl('trap_length').querySelector('[data-spec-icon-reason]')).toBeNull();
  });

  it('F3 host row shows nothing when the partner row is absent', async () => {
    mountWith([LENGTH]);
    await waitFor(() => expect(listFeatureIcons).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30));
    expect(rowEl('trap_length').querySelector('[data-spec-icon]')).toBeNull();
  });

  it('F3 several partners are joined with ", " in the hint', async () => {
    listFeatureIcons.mockResolvedValue([
      {
        ...ICONS[1],
        conditions: [
          { spec_key: 'trap_type', value: 's_trap' },
          { spec_key: 'steel_grade', value: '304' },
        ],
      },
    ]);
    mountWith([TRAP, specRow('steel_grade', 'Steel grade', '304'), LENGTH]);
    await waitFor(() => expect(rowEl('trap_length').querySelector('[data-spec-icon-reason]')).toBeTruthy());
    expect(rowEl('trap_length').querySelector('[data-spec-icon-reason]')?.textContent).toBe(
      'shown because Trap = S trap, Steel grade = 304',
    );
  });
});

describe('F3 useSpecValueIcons.iconsFor(row, rows)', () => {
  it('F3 takes the product whole rows as its second argument', async () => {
    const queryClient = new QueryClient();
    const { result } = renderHook(() => useSpecValueIcons(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      ),
    });
    await waitFor(() => expect(result.current.iconsFor(LENGTH as never, [TRAP, LENGTH] as never).length).toBe(1));
    expect(result.current.iconsFor(LENGTH as never, [LENGTH] as never)).toEqual([]);
    expect(screen.queryByText('x')).toBeNull();
  });
});

describe('F3 round 1: a numeric host stored as text', () => {
  it('F3 trap_length "150.0" with trap S still shows the S trap 150mm icon and the hint', async () => {
    mountWith([TRAP, { ...specRow('trap_length', 'Trap length', '150.0'), dataType: 'numeric' }]);
    await waitFor(() => expect(rowEl('trap_length').querySelector('[data-spec-icon="s150"]')).toBeTruthy());
    expect(rowEl('trap_length').querySelector('[data-spec-icon-reason]')?.textContent).toBe(
      'shown because Trap = S trap',
    );
  });
});

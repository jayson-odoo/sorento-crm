/**
 * NON-CANCELLABLE-ITEMS: the company default list. Rows show target, type, Yes/No and notes;
 * Add item is offered once, in the toolbar. Values invented.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
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
  usePathname: () => '/project-sales/non-cancellable',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));

const rules = vi.hoisted(() => ({
  data: [
    {
      id: 'r1',
      product_id: 'p1',
      product_code: 'ZZT-TUB-1',
      product_name: 'Freestanding bathtub',
      category_id: null,
      category_name: null,
      non_cancellable: true,
      notes: 'Bulky',
      updated_at: '2026-11-10T08:00:00',
    },
    {
      id: 'r2',
      product_id: null,
      product_code: null,
      category_id: 'c1',
      category_name: 'Bathtubs',
      non_cancellable: false,
      notes: null,
      updated_at: null,
    },
  ],
}));

vi.mock('../../_shared/hooks/useProjects', () => ({
  NON_CANCELLABLE_RULES_KEY: ['project-non-cancellable-rules'],
  useNonCancellableRules: () => ({
    data: rules.data,
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
}));
vi.mock('./NonCancellableRuleDialog', () => ({ NonCancellableRuleDialog: () => null }));

import { NonCancellableListClient } from './NonCancellableListClient';

beforeEach(() => vi.clearAllMocks());

describe('NonCancellableListClient', () => {
  it('lists each rule with its target, type and answer', () => {
    render(<NonCancellableListClient />);
    expect(screen.getByText('ZZT-TUB-1 Freestanding bathtub')).toBeInTheDocument();
    expect(screen.getByText('Bathtubs')).toBeInTheDocument();
    expect(screen.getByText('Product')).toBeInTheDocument();
    expect(screen.getByText('Category')).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument();
    expect(screen.getByText('No')).toBeInTheDocument();
    expect(screen.getByText('Bulky')).toBeInTheDocument();
  });

  it('offers Add item once, in the toolbar', () => {
    render(<NonCancellableListClient />);
    const buttons = screen.getAllByRole('button', { name: /Add item/i });
    expect(buttons).toHaveLength(1);
    expect(buttons[0].closest('[data-slot="card-header"]')).not.toBeNull();
  });
});

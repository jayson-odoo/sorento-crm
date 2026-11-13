/**
 * NON-CANCELLABLE-ITEMS: the company default list. Rows show target, type, Yes/No and notes;
 * Create is offered once, in the toolbar; row actions live on the row's right-click menu, never as
 * icon buttons on the row (owner standing rules). Values invented.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
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
const removal = vi.hoisted(() => ({ run: vi.fn() }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: removal.run, targetId: null, isPending: false, countdown: null }),
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

  it('offers Create once, in the toolbar, and no Add item', () => {
    render(<NonCancellableListClient />);
    const buttons = screen.getAllByRole('button', { name: /^Create$/ });
    expect(buttons).toHaveLength(1);
    expect(buttons[0].closest('[data-slot="card-header"]')).not.toBeNull();
    expect(screen.queryByRole('button', { name: /Add item/i })).toBeNull();
  });

  it('puts no action icon button on a row', () => {
    render(<NonCancellableListClient />);
    const row = screen.getByText('Bathtubs').closest('tr')!;
    expect(within(row).queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /^Delete/ })).toBeNull();
  });

  it('offers Edit and Delete on the row right-click menu; Delete starts the countdown', async () => {
    render(<NonCancellableListClient />);
    fireEvent.contextMenu(screen.getByText('Bathtubs'));
    expect(await screen.findByRole('menuitem', { name: 'Edit' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }));
    expect(removal.run).toHaveBeenCalledWith({ id: 'r2', subject: 'Bathtubs' });
  });
});

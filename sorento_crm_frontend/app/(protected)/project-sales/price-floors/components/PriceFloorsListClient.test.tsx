/**
 * #1335: one CTA per page. The toolbar's "Add floor" is the only offer this listing
 * makes; the empty grid does not repeat it.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
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

const push = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/price-floors',
  useRouter: () => ({ push, replace: vi.fn() }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('../../_shared/hooks/useProjects', () => ({
  usePriceFloors: () => ({ data: [], isLoading: false, isFetching: false, refetch: vi.fn() }),
}));

import { PriceFloorsListClient } from './PriceFloorsListClient';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PriceFloorsListClient', () => {
  it('offers Add floor once, in the toolbar, and not again in the empty state', () => {
    render(<PriceFloorsListClient />);

    const buttons = screen.getAllByRole('button', { name: /Add floor/i });
    expect(buttons).toHaveLength(1);
    expect(buttons[0].closest('[data-slot="card-header"]')).not.toBeNull();

    fireEvent.click(buttons[0]);
    expect(push).toHaveBeenCalledWith('/project-sales/price-floors/new');
  });
});

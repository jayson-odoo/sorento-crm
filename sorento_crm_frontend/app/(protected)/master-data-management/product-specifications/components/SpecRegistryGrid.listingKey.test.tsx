/**
 * S-6 (review round 2) - the list's column preferences move to a new listing key,
 * so a viewer who saved visibility for Code, Rules and Built in before those
 * started hidden (AC-S3.1) gets the new defaults instead of the old blob.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/master-data-management/product-specifications',
  useSearchParams: () => new URLSearchParams(''),
}));

const useListingColumnPreferences = vi.fn<
  (args: { listingKey: string | null }) => { resetToDefaults: () => void; isLoading: boolean }
>(() => ({ resetToDefaults: vi.fn(), isLoading: false }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: (args: { listingKey: string | null }) => useListingColumnPreferences(args),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

// The countdown engine itself is `hooks/useDeferredBulkAction.test.tsx`'s job -
// this only pins that the grid wires the USER-sourced selection into `run()`.
const bulkDeletionRun = vi.fn();
vi.mock('@/hooks/useDeferredBulkAction', () => ({
  useDeferredBulkAction: () => ({ run: bulkDeletionRun, isStarting: false }),
}));

const getSpecRegistry = vi.fn();
const getKeysForProduct = vi.fn();
vi.mock('../services/productSpecService', () => ({
  getSpecRegistry: (...a: unknown[]) => getSpecRegistry(...a),
  getKeysForProduct: (...a: unknown[]) => getKeysForProduct(...a),
}));

// D5 (fix round 3): "Product class" reads its Choices count off the category
// master, not `allowed_values.length` - see the SpecRegistryGrid.classChoices
// test below.
const getProductClassLabels = vi.fn().mockResolvedValue([]);
vi.mock('../../product-categories/services/categoryService', () => ({
  getProductClassLabels: (...a: unknown[]) => getProductClassLabels(...a),
}));

import { SpecRegistryGrid } from './SpecRegistryGrid';

describe('S-6 - the registry list keeps its column preferences under a new key', () => {
  it('asks the preferences hook for master_data.spec_registry.view::v2', async () => {
    getSpecRegistry.mockResolvedValue({
      keys: [
        {
          spec_key: 'finish',
          label: 'Finish',
          data_type: 'enum',
          unit: null,
          allowed_values: ['chrome'],
          excluded_values: [],
          user_values: [],
          suppressed_values: [],
          value_weights: {},
          derivation_rules: [],
          effective_rules: [],
          synonyms: {},
          applies_when: {},
          read_from: 'rules',
          rank_weight: null,
          measured_coverage: 1,
          source: 'seed',
          user_synonyms: {},
          suppressed_synonyms: {},
          match_tolerance: 0,
          match_decay: 0,
          is_active: true,
        },
      ],
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SpecRegistryGrid />
      </QueryClientProvider>,
    );
    await screen.findByText('Finish');

    const keys = useListingColumnPreferences.mock.calls.map(([args]) => args.listingKey);
    expect(keys).toContain('master_data.spec_registry.view::v2');
    expect(keys).not.toContain('master_data.spec_registry.view');
  });
});

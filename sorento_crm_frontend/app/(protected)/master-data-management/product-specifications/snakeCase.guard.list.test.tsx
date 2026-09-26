/**
 * D15 (owner ruling, 27 Sep 2026, "make sure no snake case") - the list never
 * renders a value with an underscore between word characters. See the sibling
 * `snakeCase.guard.*.test.tsx` files for the other four screens this guard
 * covers (one screen's mocks per file - `vi.mock` hoists per file, so mixing
 * conflicting mocks of the same module across screens in one file is unsafe).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const SNAKE_CASE = /\w_\w/;

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/master-data-management/product-specifications',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const getSpecRegistry = vi.fn();
const getKeysForProduct = vi.fn();
vi.mock('./services/productSpecService', () => ({
  getSpecRegistry: (...a: unknown[]) => getSpecRegistry(...a),
  getKeysForProduct: (...a: unknown[]) => getKeysForProduct(...a),
}));

import { SpecRegistryGrid } from './components/SpecRegistryGrid';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  getKeysForProduct.mockResolvedValue({ code: '', matched_product: null, keys: {} });
  getSpecRegistry.mockResolvedValue({
    keys: [
      {
        spec_key: 'capacity_oz',
        label: 'Capacity (oz)',
        data_type: 'numeric',
        unit: 'oz',
        allowed_values: [],
        excluded_values: [],
        user_values: [],
        suppressed_values: [],
        value_weights: {},
        derivation_rules: [],
        effective_rules: [],
        synonyms: { _self: ['oz'] },
        applies_when: {},
        read_from: 'rules',
        rank_weight: null,
        measured_coverage: 3,
        source: 'seed',
        user_synonyms: {},
        suppressed_synonyms: {},
        match_tolerance: 0,
        match_decay: 0,
        is_active: true,
      },
    ],
  });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('D15 guard - the Product Specifications list', () => {
  it('renders no text matching /\\w_\\w/', async () => {
    const { container } = render(withClient(<SpecRegistryGrid />));
    await screen.findByText('Capacity (oz)');
    const match = (container.textContent ?? '').match(SNAKE_CASE);
    expect(match, `rendered a snake_case value: "${match?.[0]}"`).toBeNull();
  });
});

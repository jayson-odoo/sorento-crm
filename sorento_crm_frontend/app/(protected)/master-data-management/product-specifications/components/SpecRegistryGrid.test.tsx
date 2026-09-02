/**
 * AC-A.2, AC-G.8 - the registry grid renders, filters and opens a specification.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/master-data-management/product-specifications',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getSpecRegistry = vi.fn();
const getKeysForProduct = vi.fn();
vi.mock('../services/productSpecService', () => ({
  getSpecRegistry: (...a: unknown[]) => getSpecRegistry(...a),
  getKeysForProduct: (...a: unknown[]) => getKeysForProduct(...a),
}));

import { SpecRegistryGrid } from './SpecRegistryGrid';

function baseKey(overrides: Record<string, unknown> = {}) {
  return {
    spec_key: 'finish',
    label: 'Finish',
    data_type: 'enum',
    unit: null,
    allowed_values: ['chrome', 'black'],
    excluded_values: [],
    user_values: [],
    suppressed_values: [],
    value_weights: {},
    derivation_rules: [],
    effective_rules: [{ match: 'contains', pattern: 'chrome' }],
    rules_are_default: true,
    synonyms: {},
    applies_when: {},
    read_from: 'rules',
    rank_weight: null,
    measured_coverage: 42,
    source: 'seed',
    user_synonyms: {},
    suppressed_synonyms: {},
    match_tolerance: 0,
    match_decay: 0,
    is_active: true,
    ...overrides,
  };
}

const ROWS = [
  baseKey({ spec_key: 'finish', label: 'Finish', measured_coverage: 42 }),
  baseKey({
    spec_key: 'bowl_count',
    label: 'Bowl count',
    data_type: 'numeric',
    unit: 'mm',
    allowed_values: [],
    effective_rules: [],
    measured_coverage: 5,
    source: 'user',
  }),
];

function renderGrid() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SpecRegistryGrid />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  push.mockReset();
  getSpecRegistry.mockReset();
  getKeysForProduct.mockReset();
  getSpecRegistry.mockResolvedValue({ keys: ROWS });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('SpecRegistryGrid', () => {
  it('renders every specification, sorted by label', async () => {
    renderGrid();

    expect(await screen.findByText('Bowl count')).toBeInTheDocument();
    expect(screen.getByText('Finish')).toBeInTheDocument();

    const labels = screen
      .getAllByRole('row')
      .map((row) => row.textContent || '')
      .filter((text) => text.includes('Bowl count') || text.includes('Finish'));
    expect(labels[0]).toContain('Bowl count');
    expect(labels[1]).toContain('Finish');
  });

  it('filters client-side on label, code and synonym', async () => {
    renderGrid();
    await screen.findByText('Finish');

    fireEvent.change(screen.getByPlaceholderText(/Find a specification/i), {
      target: { value: 'bowl' },
    });

    await waitFor(() => expect(screen.queryByText('Finish')).not.toBeInTheDocument());
    expect(screen.getByText('Bowl count')).toBeInTheDocument();
  });

  it('a row opens its record page, carrying the list state', async () => {
    renderGrid();
    await screen.findByText('Finish');

    const row = screen
      .getAllByRole('row')
      .find((el) => el.getAttribute('tabindex') === '0' && el.textContent?.includes('Finish')) as HTMLElement;
    expect(row).toBeTruthy();

    fireEvent.click(row);

    expect(push).toHaveBeenCalledWith(
      expect.stringContaining('/master-data-management/product-specifications/finish'),
    );
  });

  it('narrows to a matched product code and shows a dismissible pill', async () => {
    getKeysForProduct.mockResolvedValue({
      code: 'WC-100',
      matched_product: { id: 'p1', product_code: 'WC-100' },
      keys: { finish: { value: 'chrome', source: 'derived' } },
    });
    renderGrid();
    await screen.findByText('Finish');

    fireEvent.change(screen.getByPlaceholderText(/Find a specification/i), {
      target: { value: 'WC-100' },
    });

    expect(await screen.findByText(/Specifications of WC-100/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('Bowl count')).not.toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(/Clear the WC-100 filter/i));
    await waitFor(() =>
      expect(screen.queryByText(/Specifications of WC-100/i)).not.toBeInTheDocument(),
    );
    expect(screen.getByText('Bowl count')).toBeInTheDocument();
  });

  it('shows an empty state when nothing matches', async () => {
    renderGrid();
    await screen.findByText('Finish');

    fireEvent.change(screen.getByPlaceholderText(/Find a specification/i), {
      target: { value: 'no such specification exists' },
    });

    expect(await screen.findByText(/No specifications match that search/i)).toBeInTheDocument();
  });
});

/**
 * AC-A.2, AC-G.8 - the registry grid renders, filters and opens a specification.
 * D13/D14 - the toolbar reads like the Products list, and bulk delete skips seed
 * rows, reporting the skip.
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

import { toast } from '@/lib/toast';
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
  bulkDeletionRun.mockReset();
  vi.mocked(toast.warning).mockReset();
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

describe('SpecRegistryGrid - row menu (D14, D15, D15b)', () => {
  /** Radix opens on pointerdown, not click. */
  function openMenu(trigger: HTMLElement) {
    fireEvent.pointerDown(trigger, new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
  }

  it('both a seed and a user row carry the "..." menu, Delete disabled on the seed row', async () => {
    renderGrid();
    await screen.findByText('Finish');

    // The gear is always present (D15b) - Finish is source: 'seed', Bowl count is 'user'.
    // The grid is sorted by label, so Bowl count comes first, Finish second.
    const menuButtons = screen.getAllByRole('button', { name: 'specification actions' });
    expect(menuButtons).toHaveLength(2);

    openMenu(menuButtons[1]); // Finish's row (seed)
    const item = await screen.findByRole('menuitem', { name: 'Delete specification' });
    expect(item).toHaveAttribute('aria-disabled', 'true');
  });

  it('a user-made row with the delete permission has Delete enabled', async () => {
    renderGrid();
    await screen.findByText('Finish');

    const menuButtons = screen.getAllByRole('button', { name: 'specification actions' });
    openMenu(menuButtons[0]); // Bowl count's row - source: 'user'
    const item = await screen.findByRole('menuitem', { name: 'Delete specification' });
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
  });
});

describe('SpecRegistryGrid - bulk delete skips seed rows (D14)', () => {
  it('parks the deferred bulk action for the user row only, and reports the seed skip', async () => {
    renderGrid();
    await screen.findByText('Finish');

    fireEvent.click(screen.getByLabelText('Select Finish')); // seed
    fireEvent.click(screen.getByLabelText('Select Bowl count')); // user

    fireEvent.click(await screen.findByRole('button', { name: /Delete selected/i }));

    expect(bulkDeletionRun).toHaveBeenCalledWith([{ id: 'bowl_count' }]);
    expect(toast.warning).toHaveBeenCalledWith('1 skipped (shipped with the product)');
  });

  it('runs nothing and still reports the skip when only seed rows are selected', async () => {
    renderGrid();
    await screen.findByText('Finish');

    fireEvent.click(screen.getByLabelText('Select Finish')); // seed only

    fireEvent.click(await screen.findByRole('button', { name: /Delete selected/i }));

    expect(bulkDeletionRun).not.toHaveBeenCalled();
    expect(toast.warning).toHaveBeenCalledWith('1 skipped (shipped with the product)');
  });
});

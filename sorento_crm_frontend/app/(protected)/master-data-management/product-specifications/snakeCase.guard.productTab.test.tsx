/**
 * D15 - a product's Specifications tab never renders a raw slug: the values
 * table, the Add specification picker and Read values all carry a `rose_gold`
 * value with no `value_labels` override for the tab to fall back on.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const SNAKE_CASE = /\w_\w/;

const useProductSpecTable = vi.fn();
vi.mock('../products/hooks/useProductSpecTable', () => ({
  useProductSpecTable: (...a: unknown[]) => useProductSpecTable(...a),
}));
vi.mock('../products/hooks/useProducts', () => ({
  useProduct: () => ({
    data: {
      id: 'p-1',
      product_code: 'SRTBM2201-RG',
      product_name: 'SRTBM2201-RG',
      list_price: null,
      price_tag_description: null,
    },
    isLoading: false,
  }),
  useUpdateProduct: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissionSet: new Set(['master_data.products.edit']) }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ProductSpecificationsTab from '../products/[id]/components/ProductSpecificationsTab';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

useProductSpecTable.mockReturnValue({
  detail: {
    product_id: 'p-1',
    product_code: 'SRTBM2201-RG',
    category_code: 'BR-BM',
    searchable: true,
    diagnosis: { reason: 'eligible', class_label: 'Basin Mixer', brand_hint: null, suffix: null },
    spec: {
      values: { finish: { value: 'rose_gold' } },
      provenance: { finish: { source: 'code', confidence: 1, evidence: '-RG' } },
      rendered_text: 'Rose gold basin mixer',
      status: 'derived',
      derived_at: '2026-08-01T09:00:00',
    },
    exceptions: [],
    source_text: 'SRTBM2201-RG',
    verification: {
      state: 'unverified',
      verified_by_name: null,
      verified_at: null,
      invalidated_at: null,
      invalidated_reason: null,
      invalidated_by_name: null,
      invalidated_diff: null,
    },
    values_hash: 'hash-1',
  },
  rows: [
    {
      specKey: 'finish',
      label: 'Finish or colour',
      value: 'rose_gold',
      unit: null,
      dataType: 'enum',
      options: ['rose_gold'],
      source: 'code',
      evidence: '-RG',
      unknownKey: false,
      valueLabels: {},
      conflict: null,
    },
  ],
  registry: [
    {
      spec_key: 'finish',
      label: 'Finish or colour',
      data_type: 'enum',
      unit: null,
      allowed_values: ['rose_gold'],
      synonyms: {},
    },
  ],
  applicableKeys: [],
  otherKeys: [],
  heldKeys: [],
  isLoading: false,
  error: null,
  refetch: vi.fn(),
  verify: vi.fn(),
  unverify: vi.fn(),
  verificationBusy: false,
  setValue: vi.fn(),
  tombstone: vi.fn(),
  revert: vi.fn(),
  addValue: vi.fn(),
  createKey: vi.fn(),
  checkSimilarKey: vi.fn(),
});

describe('D15 guard - a product Specifications tab', () => {
  it('the values table and Read values read "Rose gold", never rose_gold', async () => {
    const { container } = render(withClient(<ProductSpecificationsTab productId="p-1" />));
    await screen.findByText('Rose gold basin mixer');
    // "Rose gold" is present somewhere in the values table (cell text may be
    // split across nodes with the source pill, so a substring check on the
    // whole tree rather than an exact node match).
    expect(container.textContent ?? '').toContain('Rose gold');
    const match = (container.textContent ?? '').match(SNAKE_CASE);
    expect(match, `rendered a snake_case value: "${match?.[0]}"`).toBeNull();
  });
});

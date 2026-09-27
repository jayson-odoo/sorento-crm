/**
 * S-15 (review round 2) - the product tab's search box goes through a hook, sends
 * the phrase once, and never lets a slower, earlier answer overwrite the answer to
 * the phrase typed after it.
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ProductSpecificationsTab from './ProductSpecificationsTab';
import type { ProductSpecDetail } from '../../../product-specifications/types/productSpec.types';
import type { VerificationBlock } from '../../../spec-verification/types/specVerification.types';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock('@/components/spec-table', () => ({
  SpecTable: () => <div data-testid="spec-table-stub" />,
  AddSpecificationDialog: () => null,
}));

const usePermissions = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => usePermissions(),
}));

// `CheckedLine` parks the real `spec_verification.unverify` deferred action
// (fix round 1) - nothing here exercises it, so the service only needs to
// resolve to "nothing pending" without ever being asked to create one.
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

const useProductSpecTable = vi.fn();
vi.mock('../../hooks/useProductSpecTable', () => ({
  DETAIL_KEY: (productId: string) => ['product-spec-detail', productId],
  useProductSpecTable: (...a: unknown[]) => useProductSpecTable(...a),
}));

vi.mock('../../hooks/useProducts', () => ({
  useProduct: () => ({
    data: { id: 'p-1', product_code: 'WC100', product_name: 'WC100', list_price: null, price_tag_description: null },
    isLoading: false,
  }),
  useUpdateProduct: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const previewSpecSearch = vi.fn();
vi.mock('../../../product-specifications/services/productSpecService', () => ({
  previewSpecSearch: (...a: unknown[]) => previewSpecSearch(...a),
}));

const VERIFIED: VerificationBlock = {
  state: 'verified',
  verified_by_name: 'Jay Odoo',
  verified_at: '2026-08-10T09:00:00',
  invalidated_at: null,
  invalidated_reason: null,
  invalidated_by_name: null,
  invalidated_diff: null,
};

function baseDetail(renderedText: string | null): ProductSpecDetail {
  return {
    product_id: 'p-1',
    product_code: 'WC100',
    category_code: 'BR-KS',
    searchable: true,
    diagnosis: { reason: 'eligible', class_label: 'Kitchen Sink', brand_hint: null, suffix: null },
    spec: {
      values: {},
      provenance: {},
      rendered_text: renderedText,
      status: 'authored',
      derived_at: '2026-08-01T09:00:00',
    },
    exceptions: [],
    source_text: 'WC100',
    verification: VERIFIED,
    values_hash: 'hash-1',
  } as ProductSpecDetail;
}

function mockHook(detail: ProductSpecDetail) {
  useProductSpecTable.mockReturnValue({
    detail,
    rows: [],
    registry: [],
    applicableKeys: [],
    otherKeys: [],
    heldKeys: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    verify: vi.fn(),
    verificationBusy: false,
    setValue: vi.fn(),
    tombstone: vi.fn(),
    revert: vi.fn(),
    addValue: vi.fn(),
    createKey: vi.fn(),
    checkSimilarKey: vi.fn(),
  });
}

/** `useDeferredAction` inside `CheckedLine` is real (only the service is mocked),
 * so it needs a live `QueryClient` under it. */
function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProductSpecificationsTab productId="p-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  usePermissions.mockReturnValue({ permissionSet: new Set(['master_data.products.edit']) });
});

afterEach(() => cleanup());

function candidate(productId: string) {
  return { product_id: productId, product_code: productId, summary: '', class: null, matched_specs: [], score: 1, is_discontinued: false };
}
function answer(ids: string[]) {
  return { candidates: ids.map(candidate), floor_missed: false, top_score: 1, floor: 0, understanding: null, unmet: [] };
}

function search(text: string) {
  const box = screen.getByPlaceholderText('Type what a customer would ask');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: 'Enter' });
}

describe('S-15 - the search box', () => {
  it('sends the phrase once: as the phrase, never again inside free_terms', async () => {
    previewSpecSearch.mockResolvedValue(answer(['p-1']));
    mockHook(baseDetail('Water closet'));
    renderTab();

    search('one piece toilet');
    await screen.findByText('This product comes up, 1st of 1');

    expect(previewSpecSearch).toHaveBeenCalledTimes(1);
    const body = previewSpecSearch.mock.calls[0][0] as { phrase: string; free_terms: string[] };
    expect(body.phrase).toBe('one piece toilet');
    expect(body.free_terms).not.toContain('one piece toilet');
    expect(JSON.stringify(body).split('one piece toilet').length - 1).toBe(1);
  });

  it('a slower answer to an earlier phrase never overwrites the answer to the later one', async () => {
    let resolveFirst: (value: unknown) => void = () => {};
    previewSpecSearch
      .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
      .mockImplementationOnce(async () => answer(['p-1']));
    mockHook(baseDetail('Water closet'));
    renderTab();

    search('basin');
    search('one piece toilet');
    await screen.findByText('This product comes up, 1st of 1');

    // The first request answers last, and says the product does not come up.
    resolveFirst(answer(['other-1']));
    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(screen.getByText('This product comes up, 1st of 1')).toBeInTheDocument();
    expect(screen.queryByText('This product does not come up for this')).toBeNull();
  });
});

describe('N-R7 (review round 3) - Enter again on the same phrase', () => {
  it('runs the search again', async () => {
    previewSpecSearch.mockResolvedValue(answer(['p-1']));
    mockHook(baseDetail('Water closet'));
    renderTab();

    search('one piece toilet');
    await screen.findByText('This product comes up, 1st of 1');
    expect(previewSpecSearch).toHaveBeenCalledTimes(1);

    search('one piece toilet');
    await waitFor(() => expect(previewSpecSearch).toHaveBeenCalledTimes(2));
  });
});

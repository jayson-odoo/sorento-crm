/**
 * ProductSpecificationsTab - Reading and search (AC-S2.1, AC-S2.5, AC-S2.10, D9).
 *
 * The section holds exactly two things: the read values line, and one search box
 * that runs the existing preview search and answers in one line. No score, no
 * matched keys, no understanding panel, no "Read this product again" button.
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

describe('Reading and search - two things only (AC-S2.1, AC-S2.5)', () => {
  it('renders the read values line', () => {
    mockHook(baseDetail('Water closet, One piece, Twister flush'));
    renderTab();

    expect(screen.getByText('Reading and search')).toBeInTheDocument();
    expect(screen.getByText('Read values')).toBeInTheDocument();
    expect(screen.getByText('Water closet, One piece, Twister flush')).toBeInTheDocument();
  });

  it('reads "Nothing read yet." when nothing was read', () => {
    mockHook(baseDetail(null));
    renderTab();

    expect(screen.getByText('Nothing read yet.')).toBeInTheDocument();
  });

  it('renders no score, no matched-keys badge, no understanding panel, no re-read button', () => {
    mockHook(baseDetail('Water closet'));
    renderTab();

    expect(screen.queryByText(/Understood as/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /read this product again/i })).not.toBeInTheDocument();
  });
});

describe('Reading and search - the search box (AC-S2.10)', () => {
  it('answers "This product comes up, Nth of M" when the product is among the candidates', async () => {
    previewSpecSearch.mockResolvedValue({
      candidates: [
        { product_id: 'other-1', product_code: 'X', summary: '', class: null, matched_specs: [], score: 1, is_discontinued: false },
        { product_id: 'p-1', product_code: 'WC100', summary: '', class: null, matched_specs: [], score: 1, is_discontinued: false },
      ],
      floor_missed: false,
      top_score: 1,
      floor: 0,
      understanding: null,
      unmet: [],
    });
    mockHook(baseDetail('Water closet'));
    renderTab();

    const box = screen.getByPlaceholderText('Type what a customer would ask');
    fireEvent.change(box, { target: { value: 'one piece toilet twister' } });
    fireEvent.keyDown(box, { key: 'Enter' });

    expect(await screen.findByText('This product comes up, 2nd of 2')).toBeInTheDocument();
  });

  it('answers "This product does not come up for this" when the product is not among the candidates', async () => {
    previewSpecSearch.mockResolvedValue({
      candidates: [
        { product_id: 'other-1', product_code: 'X', summary: '', class: null, matched_specs: [], score: 1, is_discontinued: false },
      ],
      floor_missed: false,
      top_score: 1,
      floor: 0,
      understanding: null,
      unmet: [],
    });
    mockHook(baseDetail('Water closet'));
    renderTab();

    const box = screen.getByPlaceholderText('Type what a customer would ask');
    fireEvent.change(box, { target: { value: 'stainless steel basin' } });
    fireEvent.keyDown(box, { key: 'Enter' });

    expect(await screen.findByText('This product does not come up for this')).toBeInTheDocument();
    await waitFor(() => expect(previewSpecSearch).toHaveBeenCalled());
  });
});

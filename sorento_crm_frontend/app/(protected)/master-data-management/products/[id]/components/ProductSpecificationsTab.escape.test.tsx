/**
 * PRICETAG-COMBO-FORMAT fix round 1, R10: Escape inside a toolbar popover (Text colour) closes the
 * popover only. The description edit stays open and its draft is untouched.
 *
 * Written test-FIRST: the edit box cancels on any Escape that bubbles up from its children,
 * popover included (React bubbles a portal's events to its parent), which throws the draft away.
 * The REAL RichTextEditor is used here: the popover is part of it.
 */
import React from 'react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';
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

// The extraction panel is its own feature with its own suite; it fetches
// through react-query, which this test deliberately does not provide.
vi.mock('./SpecExtractPanel', () => ({ default: () => null }));

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

// AC-S4-10/S11: `useProduct` supplies name/list_price/`price_tag_description`
// to a component that until now only ever knew the product id;
// `useUpdateProduct` is the SAME mutation hook `ProductForm.tsx` already
// saves every other product field through.
const updateMutateAsync = vi.fn().mockResolvedValue({});
const useProduct = vi.fn();
vi.mock('../../hooks/useProducts', () => ({
  useProduct: (...a: unknown[]) => useProduct(...a),
  useUpdateProduct: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
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

const MATERIAL_KEY = {
  spec_key: 'material',
  label: 'Material',
  data_type: 'enum',
  unit: null,
  allowed_values: [],
  synonyms: {},
  value_labels: { stainless_steel: 'Stainless Steel' },
};

function baseDetail(overrides: Partial<ProductSpecDetail> = {}): ProductSpecDetail {
  return {
    product_id: 'p-1',
    product_code: 'WC100',
    category_code: 'BR-KS',
    searchable: true,
    diagnosis: { reason: 'eligible', class_label: 'Kitchen Sink', brand_hint: 'Sorento', suffix: null },
    spec: {
      values: { material: { value: 'stainless_steel' } },
      provenance: { material: { source: 'human', confidence: 1, evidence: 'manual' } },
      rendered_text: 'A stainless steel basin tap',
      status: 'authored',
      derived_at: '2026-08-01T09:00:00',
    },
    exceptions: [],
    source_text: 'WC100 basin tap',
    verification: VERIFIED,
    values_hash: 'hash-1',
    ...overrides,
  } as ProductSpecDetail;
}

/** The row `SpecTable` would render, in the exact READABLE shape the tab's
 *  own preview must read through (never the raw stored slug). */
const MATERIAL_ROW = {
  specKey: 'material',
  label: 'Material',
  value: 'stainless_steel',
  unit: null,
  dataType: 'enum',
  options: [],
  source: 'human',
  evidence: null,
  unknownKey: false,
  valueLabels: { stainless_steel: 'Stainless Steel' },
};

function mockSpecHook(
  detail: ProductSpecDetail,
  overrides: Partial<ReturnType<typeof useProductSpecTable>> = {},
) {
  useProductSpecTable.mockReturnValue({
    detail,
    rows: [MATERIAL_ROW],
    registry: [MATERIAL_KEY],
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
    ...overrides,
  });
}

function baseProduct(overrides: Record<string, unknown> = {}) {
  return {
    id: 'p-1',
    product_code: 'WC100',
    product_name: 'Basin Tap',
    list_price: 250,
    price_tag_description: 'Stored template text',
    ...overrides,
  };
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


function editButton() {
  return screen.getByRole('button', { name: /edit price tag description/i });
}

describe('Escape in the Text colour popover (R10)', () => {
  it('R10: closes the popover and keeps the edit and the draft', async () => {
    mockSpecHook(baseDetail());
    renderTab();
    fireEvent.click(editButton());
    await waitFor(() => expect(document.querySelector('[contenteditable="true"]')).not.toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Text colour' }));
    const hex = await screen.findByLabelText('Hex colour');
    fireEvent.keyDown(hex, { key: 'Escape' });

    await waitFor(() => expect(screen.queryByLabelText('Hex colour')).toBeNull());
    // Still editing: Save is there and the stored text is still in the editor.
    expect(screen.getByRole('button', { name: /^save$/i })).toBeInTheDocument();
    expect(document.querySelector('[contenteditable="true"]')?.textContent).toBe('Stored template text');
    expect(updateMutateAsync).not.toHaveBeenCalled();
  });

  it('R10: Escape in the editor itself still cancels the edit (unchanged)', async () => {
    mockSpecHook(baseDetail());
    renderTab();
    fireEvent.click(editButton());
    await waitFor(() => expect(document.querySelector('[contenteditable="true"]')).not.toBeNull());

    fireEvent.keyDown(document.querySelector('[contenteditable="true"]') as Element, { key: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('button', { name: /^save$/i })).toBeNull());
    expect(screen.getByText('Stored template text')).toBeInTheDocument();
  });
});

beforeEach(() => {
  vi.clearAllMocks();
  usePermissions.mockReturnValue({ permissionSet: new Set(['master_data.products.edit']) });
  useProduct.mockReturnValue({ data: baseProduct(), isLoading: false });
});
afterEach(() => cleanup());
